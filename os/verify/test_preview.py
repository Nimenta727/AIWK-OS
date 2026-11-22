"""Static project preview: strict path resolution, headers, Host check, idle stop, and the workbench API around it."""
import http.client
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
import aiws_preview as P
from aiws_workbench import make_server, HOST

class Tree(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.base = Path(self.t.name).resolve(); self.site = self.base / "site"; self.site.mkdir()
        (self.site / "index.html").write_text("<h1>home</h1>"); (self.site / "app.js").write_text("console.log(1)"); (self.site / "sub").mkdir(); (self.site / "sub" / "index.html").write_text("sub")
        (self.site / "data.json").write_text("{}"); (self.site / ".env").write_text("SECRET=1"); (self.site / ".git").mkdir(); (self.site / ".git" / "config").write_text("x")
        (self.base / "outside.txt").write_text("OUTSIDE"); (self.site / "nodots").mkdir(); (self.site / "empty").mkdir()
        os.symlink(self.base / "outside.txt", self.site / "link.txt"); os.symlink(self.base, self.site / "dirlink")
        self.addCleanup(self.t.cleanup)

class Resolve(Tree):
    def test_serves_files_and_folder_index(self):
        for url, name in (("/", "index.html"), ("/index.html", "index.html"), ("/app.js", "app.js"), ("/sub", "index.html"), ("/sub/", "index.html"), ("//app.js", "app.js"), ("/./app.js", "app.js")):
            r = P.resolve(self.site, url); self.assertIsNotNone(r, url); self.assertEqual(r.name, name)
    def test_nothing_outside_and_nothing_hidden_or_linked(self):
        for url in ("/../outside.txt", "/..%2foutside.txt", "/%2e%2e/outside.txt", "/%2E%2E/outside.txt", "/sub/../../outside.txt", "/link.txt", "/dirlink/outside.txt", "/.env", "/.git/config", "/.git",
                    "/%2eenv", "/sub/.hidden", "/a\\..\\outside.txt", "/app.js%00.png", "/%252e%252e/outside.txt", "/empty", "/nodots", "/missing", "/app.js/x"):
            self.assertIsNone(P.resolve(self.site, url), url)
    def test_no_directory_listing(self):
        self.assertIsNone(P.resolve(self.site, "/empty"))
    def test_an_index_that_is_a_symlink_is_not_followed(self):
        (self.site / "empty" / "index.html").symlink_to(self.base / "outside.txt"); self.assertIsNone(P.resolve(self.site, "/empty/"))

class Server(Tree):
    def setUp(self):
        super().setUp(); self.pv = P.Preview(self.site); self.addCleanup(self.pv.stop)
    def get(self, path, method="GET", host=None, port=None):
        c = http.client.HTTPConnection("127.0.0.1", port or self.pv.port, timeout=10)
        c.request(method, path, headers={"Host": host if host is not None else "127.0.0.1:%d" % self.pv.port}); r = c.getresponse(); body = r.read(); h = dict(r.getheaders()); c.close(); return r.status, h, body
    def test_serves_with_safe_headers(self):
        s, h, b = self.get("/"); self.assertEqual((s, b), (200, b"<h1>home</h1>"))
        self.assertEqual((h["Cache-Control"], h["X-Content-Type-Options"], h["Referrer-Policy"]), ("no-store", "nosniff", "no-referrer"))
        self.assertIn("text/html", h["Content-Type"]); self.assertIn("default-src 'self'", h["Content-Security-Policy"]); self.assertIn("frame-ancestors http://127.0.0.1:*", h["Content-Security-Policy"])
        self.assertIn("text/javascript", self.get("/app.js")[1]["Content-Type"]); self.assertNotIn("Content-Security-Policy", self.get("/app.js")[1]); self.assertIn("application/json", self.get("/data.json")[1]["Content-Type"])
    def test_attacks_get_404_not_content(self):
        for path in ("/../outside.txt", "/..%2foutside.txt", "/link.txt", "/dirlink/outside.txt", "/.env", "/.git/config"):
            s, _, b = self.get(path); self.assertEqual(s, 404, path); self.assertNotIn(b"OUTSIDE", b); self.assertNotIn(b"SECRET", b)
    def test_raw_dot_dot_on_the_wire_is_still_contained(self):
        c = http.client.HTTPConnection("127.0.0.1", self.pv.port); c.putrequest("GET", "/../outside.txt", skip_host=True); c.putheader("Host", "127.0.0.1:%d" % self.pv.port); c.endheaders()
        r = c.getresponse(); self.assertEqual(r.status, 404); self.assertNotIn(b"OUTSIDE", r.read())
    def test_only_get_and_head(self):
        for m in ("POST", "PUT", "DELETE", "PATCH", "OPTIONS"): self.assertEqual(self.get("/", m)[0], 405, m)
        s, h, b = self.get("/", "HEAD"); self.assertEqual((s, b, h["Content-Length"]), (200, b"", "13"))
    def test_wrong_host_header_is_refused_so_dns_rebinding_fails(self):
        for host in ("evil.example", "evil.example:%d" % self.pv.port, "127.0.0.1", "127.0.0.1:1", "", "localhost"):
            self.assertEqual(self.get("/", host=host)[0], 403, host)
        self.assertEqual(self.get("/", host="localhost:%d" % self.pv.port)[0], 200)
    def test_big_files_are_refused(self):
        old = P.MAX_FILE; P.MAX_FILE = 5
        try: self.assertEqual(self.get("/index.html")[0], 413)
        finally: P.MAX_FILE = old
    def test_binds_loopback_only(self):
        self.assertEqual(self.pv.server.server_address[0], "127.0.0.1")
    def test_stops_by_itself_when_idle_and_touch_postpones_it(self):
        t = [0.0]; pv = P.Preview(self.site, idle_seconds=5, clock=lambda: t[0]); self.addCleanup(pv.stop)
        t[0] = 4; pv.touch(); t[0] = 8; time.sleep(0.8); self.assertFalse(pv.stopped.is_set())
        t[0] = 20; self.assertTrue(pv.stopped.wait(3))
        refused = False
        for _ in range(30):                                        # the flag is set just before the socket is closed
            try: http.client.HTTPConnection("127.0.0.1", pv.port, timeout=1).connect(); time.sleep(0.1)
            except OSError: refused = True; break
        self.assertTrue(refused, "the port is still listening after the idle stop")

class Api(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); base = Path(self.temp.name); self.root = (base / "workspace"); self.root.mkdir(); self.root = self.root.resolve()
        (self.root / "site").mkdir(); (self.root / "site" / "index.html").write_text("<p>hi</p>"); (self.root / "secret.txt").write_text("S")
        ui = base / "ui"; (ui / "assets").mkdir(parents=True); (ui / "index.html").write_text("<html><head></head><body></body></html>")
        self.env = patch.dict(os.environ, {"AIWS_WORKSPACE": str(self.root), "XDG_STATE_HOME": str(base / "state"), "AIWS_SKILLS_DIR": str(base / "none")}); self.env.start()
        self.cfgs = [patch("aiws_workbench.load_config", lambda: {"externalEnabled": False, "providers": {}, "extraLocalKeywords": [], "extraExternalKeywords": []}),
                     patch("aiws_workbench.load_builder_config", lambda: {"enabled": False, "envAllow": [], "isolation": {"mode": "none", "user": "x", "proxy": "http://127.0.0.1:3128"}, "execWithoutIsolation": False})]
        [p.start() for p in self.cfgs]
        self.server = make_server(self.root, ui, 0); threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.hdr = {"X-AIWS-CSRF": json.loads(self.raw("GET", "/api/v1/session")[1])["csrf"]}
    def tearDown(self):
        self.server.application.preview.stop(); self.server.shutdown(); self.server.server_close()
        a = self.server.application; a.pool.shutdown(wait=True, cancel_futures=True); time.sleep(0.2); a.tasks.close(); a.events.close(); a.mandates.close()
        [p.stop() for p in self.cfgs]; self.env.stop(); self.temp.cleanup()
    def raw(self, method, path, payload=None, headers=None):
        c = http.client.HTTPConnection(HOST, self.server.server_port, timeout=10); h = {"Host": HOST + ":" + str(self.server.server_port), **(headers or {})}; body = None
        if payload is not None: body = json.dumps(payload); h["Content-Type"] = "application/json"
        c.request(method, path, body=body, headers=h); r = c.getresponse(); d = r.read(); c.close(); return r.status, d
    def test_start_serve_stop_cycle(self):
        self.assertFalse(json.loads(self.raw("GET", "/api/v1/preview")[1])["running"])
        status, data = self.raw("POST", "/api/v1/preview", {"path": "site"}, self.hdr); self.assertEqual(status, 202, data); info = json.loads(data); self.assertTrue(info["running"]); self.assertEqual(info["path"], "site")
        port = int(info["url"].rsplit(":", 1)[1].strip("/")); c = http.client.HTTPConnection("127.0.0.1", port, timeout=5); c.request("GET", "/", headers={"Host": "127.0.0.1:%d" % port}); self.assertEqual(c.getresponse().read(), b"<p>hi</p>")
        time.sleep(1.1); self.assertFalse(json.loads(self.raw("POST", "/api/v1/preview/stop", {"x": 1} and {}, self.hdr)[1])["running"] if False else json.loads(self.raw("POST", "/api/v1/preview/stop", {}, self.hdr)[1])["running"])
    def test_needs_csrf_and_exact_fields(self):
        self.assertEqual(self.raw("POST", "/api/v1/preview", {"path": "site"})[0], 403)
        time.sleep(1.1); self.assertEqual(self.raw("POST", "/api/v1/preview", {"path": "site", "port": 80}, self.hdr)[0], 400)
        time.sleep(1.1); self.assertEqual(self.raw("POST", "/api/v1/preview", {"path": 5}, self.hdr)[0], 400)
    def test_the_folder_is_confined_to_the_workspace_by_the_platforms_path_rules(self):
        for bad in ("..", "../x", "/etc", "site/../../x", ".git", "secret.txt", "missing"):
            time.sleep(1.1); status, data = self.raw("POST", "/api/v1/preview", {"path": bad}, self.hdr); self.assertGreaterEqual(status, 400, bad)
        self.assertFalse(json.loads(self.raw("GET", "/api/v1/preview")[1])["running"])
    def test_starting_another_replaces_the_first(self):
        (self.root / "other").mkdir(); (self.root / "other" / "index.html").write_text("o")
        a = json.loads(self.raw("POST", "/api/v1/preview", {"path": "site"}, self.hdr)[1]); time.sleep(1.1); b = json.loads(self.raw("POST", "/api/v1/preview", {"path": "other"}, self.hdr)[1])
        self.assertNotEqual(a["url"], b["url"]); pa = int(a["url"].rsplit(":", 1)[1].strip("/"))
        with self.assertRaises(OSError): http.client.HTTPConnection("127.0.0.1", pa, timeout=1).request("GET", "/")

if __name__ == "__main__":
    unittest.main()
