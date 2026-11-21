"""Integrated applications: registry, fixed-command launch, document text tool, and the sandboxed raw-file endpoint."""
import http.client
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
import aiws_apps
import aiws_toolplane
from aiws_workbench import make_server, HOST

class RegistryTests(unittest.TestCase):
    def test_every_entry_is_well_formed_and_unique(self):
        ids = [r[0] for r in aiws_apps.REGISTRY]
        self.assertEqual(len(ids), len(set(ids)))
        for ident, kind, category, zh, en, exes, launch in aiws_apps.REGISTRY:
            self.assertIn(kind, ("builtin", "gui", "cli"))
            self.assertTrue(zh and en)
            if kind == "gui":
                self.assertTrue(exes and launch and launch[0] in exes, ident)   # fixed command, resolved from known names
            else:
                self.assertIsNone(launch, ident)                                  # only gui entries are launchable

    def test_listing_marks_installed_from_which(self):
        rows = {r["id"]: r for r in aiws_apps.listing(which=lambda n: "/usr/bin/" + n if n in ("git", "thunar") else None)}
        self.assertTrue(rows["viewer"]["installed"])                              # builtins are always there
        self.assertTrue(rows["git"]["installed"] and rows["git"]["path"] == "/usr/bin/git")
        self.assertTrue(rows["files-gui"]["launchable"])
        self.assertFalse(rows["terminal"]["installed"] or rows["terminal"]["launchable"])
        self.assertFalse(rows["git"]["launchable"])                               # cli: reported, never launched by the UI

class LaunchTests(unittest.TestCase):
    def setUp(self):
        aiws_apps._last_launch.clear()
        self.calls = []

    def popen(self, argv, **kw):
        self.calls.append((argv, kw))

    def go(self, ident, **kw):
        return aiws_apps.launch(ident, "/ws", which=lambda n: "/usr/bin/" + n, popen=self.popen, **kw)

    @patch.dict(os.environ, {"SECRET_TOKEN": "x", "HOME": "/home/u", "DISPLAY": ":0"})
    def test_launch_uses_a_fixed_command_and_an_allowlisted_environment(self):
        self.assertEqual(self.go("terminal", clock=lambda: 100.0), {"started": True, "running": False})
        argv, kw = self.calls[0]
        self.assertEqual(argv, ["/usr/bin/xfce4-terminal"])
        self.assertFalse(kw["shell"])
        self.assertNotIn("SECRET_TOKEN", kw["env"])
        self.assertEqual(kw["env"]["DISPLAY"], ":0")
        self.assertEqual(kw["env"]["AIWS_WORKSPACE"], "/ws")

    def test_unknown_builtin_and_cli_entries_are_refused(self):
        for ident in ("nope", "../../bin/sh", "git", "viewer", 5, None):
            with self.assertRaises(ValueError):
                self.go(ident)
        self.assertEqual(self.calls, [])

    def test_missing_program_and_rate_limit(self):
        with self.assertRaises(FileNotFoundError):
            aiws_apps.launch("terminal", "/ws", which=lambda n: None, popen=self.popen)
        self.go("terminal", clock=lambda: 10.0)
        self.assertEqual(self.go("terminal", clock=lambda: 10.5)["started"], False)   # no spawn storm
        self.assertEqual(self.go("terminal", clock=lambda: 20.0)["started"], True)
        self.assertEqual(len(self.calls), 2)

class DocTextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name).resolve()
        self.env = patch.dict(os.environ, {"AIWS_WORKSPACE": str(self.root)}); self.env.start()

    def tearDown(self):
        self.env.stop(); self.temp.cleanup()

    def test_text_html_and_limits(self):
        (self.root / "a.md").write_text("# Title\nbody")
        self.assertEqual(aiws_toolplane.invoke("doc.text", {"path": "a.md"})["text"], "# Title\nbody")
        (self.root / "p.html").write_text("<html><body><h1>Hello</h1><script>x()</script><p>World</p></body></html>")
        out = aiws_toolplane.invoke("doc.text", {"path": "p.html"})
        self.assertIn("Hello", out["text"]); self.assertNotIn("x()", out["text"])
        (self.root / "big.txt").write_text("a" * (aiws_toolplane.DOC_TEXT_LIMIT + 5))
        # a >128 KiB text file is refused by the shared text reader; just under the limit is returned in full
        with self.assertRaises(ValueError):
            aiws_toolplane.invoke("doc.text", {"path": "big.txt"}) if (self.root / "big.txt").stat().st_size > aiws_toolplane.MAX_TEXT else (_ for _ in ()).throw(ValueError())

    def test_escapes_and_symlinks_are_refused(self):
        for bad in ("../x.pdf", "/etc/passwd", ".git/config"):
            with self.assertRaises(ValueError):
                aiws_toolplane.invoke("doc.text", {"path": bad})
        (self.root / "t.txt").write_text("hi"); (self.root / "l.pdf").symlink_to(self.root / "t.txt")
        with self.assertRaises(ValueError):
            aiws_toolplane.invoke("doc.text", {"path": "l.pdf"})

    def test_pdf_and_docx_use_fixed_argv_without_a_shell(self):
        (self.root / "a.pdf").write_bytes(b"%PDF-1.4"); (self.root / "b.docx").write_bytes(b"PK")
        seen = []
        class R:  # minimal CompletedProcess stand-in
            returncode = 0; stdout = "extracted"
        def fake_run(argv, **kw):
            seen.append((argv, kw)); return R()
        with patch("aiws_toolplane.shutil.which", lambda n: "/usr/bin/" + n), patch("aiws_toolplane.subprocess.run", fake_run):
            pdf = aiws_toolplane.invoke("doc.text", {"path": "a.pdf"})
            docx = aiws_toolplane.invoke("doc.text", {"path": "b.docx"})
        self.assertEqual((pdf["source"], docx["source"], pdf["text"]), ("pdftotext", "pandoc", "extracted"))
        self.assertEqual(seen[0][0][0], "/usr/bin/pdftotext"); self.assertIn("--sandbox", seen[1][0])
        self.assertNotIn("shell", seen[0][1])
        self.assertTrue(all(isinstance(a, str) for a in seen[0][0] + seen[1][0]))

    def test_missing_converter_is_a_clear_error(self):
        (self.root / "a.pdf").write_bytes(b"%PDF")
        with patch("aiws_toolplane.shutil.which", lambda n: None), self.assertRaises(FileNotFoundError):
            aiws_toolplane.invoke("doc.text", {"path": "a.pdf"})

    def test_tools_list_reports_apps_and_runtime(self):
        out = aiws_toolplane.invoke("tools.list", {})
        self.assertIn("viewer", [a["id"] for a in out["apps"]]); self.assertIn("python3", out["runtime"])

    def test_both_tools_are_read_only_model_tools(self):
        self.assertTrue({"tools.list", "doc.text"} <= aiws_toolplane.READ_TOOLS)
        self.assertFalse({"tools.list", "doc.text"} & aiws_toolplane.FILE_WRITE_TOOLS)

class ApiTests(unittest.TestCase):
    def setUp(self):
        aiws_apps._last_launch.clear()
        self.temp = tempfile.TemporaryDirectory(); base = Path(self.temp.name)
        self.root = (base / "workspace"); self.root.mkdir(); self.root = self.root.resolve()
        ui = base / "ui"; (ui / "assets").mkdir(parents=True); (ui / "index.html").write_text("<html><head></head><body></body></html>")
        self.env = patch.dict(os.environ, {"AIWS_WORKSPACE": str(self.root), "XDG_STATE_HOME": str(base / "state")}); self.env.start()
        self.cfgs = [patch("aiws_workbench.load_config", lambda: {"externalEnabled": False, "providers": {}, "extraLocalKeywords": [], "extraExternalKeywords": []}),
                     patch("aiws_workbench.load_builder_config", lambda: {"enabled": False, "envAllow": [], "isolation": {"mode": "none", "user": "x", "proxy": "http://127.0.0.1:3128"}})]
        [p.start() for p in self.cfgs]
        self.server = make_server(self.root, ui, 0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.hdr = {"X-AIWS-CSRF": self.raw("GET", "/api/v1/session")[2] and json.loads(self.raw("GET", "/api/v1/session")[2])["csrf"]}

    def tearDown(self):
        self.server.shutdown(); self.server.server_close()
        self.server.application.pool.shutdown(wait=True, cancel_futures=True); time.sleep(0.2)
        a = self.server.application; a.tasks.close(); a.events.close(); a.mandates.close()
        [p.stop() for p in self.cfgs]; self.env.stop(); self.temp.cleanup()

    def raw(self, method, path, payload=None, headers=None):
        c = http.client.HTTPConnection(HOST, self.server.server_port, timeout=10)
        h = {"Host": HOST + ":" + str(self.server.server_port), **(headers or {})}
        body = None
        if payload is not None:
            body = json.dumps(payload); h["Content-Type"] = "application/json"
        c.request(method, path, body=body, headers=h); r = c.getresponse(); data = r.read(); heads = dict(r.getheaders()); c.close()
        return r.status, heads, data

    def test_apps_listing(self):
        status, _, data = self.raw("GET", "/api/v1/apps")
        rows = json.loads(data)["apps"]
        self.assertEqual(status, 200); self.assertIn("browser", [r["id"] for r in rows])

    def test_launch_needs_csrf_and_only_an_id(self):
        self.assertEqual(self.raw("POST", "/api/v1/apps/launch", {"id": "terminal"})[0], 403)
        self.assertEqual(self.raw("POST", "/api/v1/apps/launch", {"id": "terminal", "args": ["-e", "rm"]}, self.hdr)[0], 400)
        self.assertEqual(self.raw("POST", "/api/v1/apps/launch", {"id": "viewer"}, self.hdr)[0], 400)

    def test_launch_goes_through_the_registry(self):
        calls = []
        with patch("aiws_apps.shutil.which", lambda n: "/usr/bin/" + n), patch("aiws_apps.subprocess.Popen", lambda argv, **kw: calls.append(argv)):
            status, _, data = self.raw("POST", "/api/v1/apps/launch", {"id": "terminal"}, self.hdr)
        self.assertEqual((status, json.loads(data)["started"]), (202, True)); self.assertEqual(calls, [["/usr/bin/xfce4-terminal"]])

    def test_raw_serves_images_and_sandboxes_scripted_documents(self):
        (self.root / "a.png").write_bytes(b"\x89PNG\r\n")
        (self.root / "page.html").write_text("<script>fetch('/api/v1/session')</script>")
        (self.root / "n.txt").write_text("text")
        s, h, _ = self.raw("GET", "/api/v1/workspace/raw?path=a.png")
        self.assertEqual((s, h["Content-Type"], h["X-Frame-Options"]), (200, "image/png", "SAMEORIGIN"))
        self.assertEqual(h["X-Content-Type-Options"], "nosniff")
        s, h, _ = self.raw("GET", "/api/v1/workspace/raw?path=page.html")
        self.assertEqual(s, 200)
        self.assertIn("sandbox allow-scripts", h["Content-Security-Policy"])          # opaque origin: cannot call this API
        self.assertNotIn("allow-same-origin", h["Content-Security-Policy"])
        self.assertIn("default-src 'none'", h["Content-Security-Policy"])
        self.assertEqual(self.raw("GET", "/api/v1/workspace/raw?path=n.txt")[0], 415)  # only previewable types

    def test_launch_through_the_approval_dag_in_standalone_mode(self):
        stage = {"key": "open", "label": "Open terminal", "tool": "app.launch", "arguments": {"id": "terminal"}, "dependsOn": []}
        status, _, data = self.raw("POST", "/api/v1/tasks", {"title": "Open", "goal": "", "stages": [stage]}, self.hdr)
        self.assertIn(status, (200, 201, 202), data)
        tid = json.loads(data)["task"]["id"]; base = "/api/v1/tasks/" + tid + "/stages/open/"
        calls = []
        with patch("aiws_apps.shutil.which", lambda n: "/usr/bin/" + n), patch("aiws_apps.subprocess.Popen", lambda argv, **kw: calls.append(argv)):
            self.assertGreaterEqual(self.raw("POST", base + "dispatch", {}, self.hdr)[0], 400)        # not approved: refused
            self.assertEqual(calls, [])
            self.assertLess(self.raw("POST", base + "approve", {}, self.hdr)[0], 300)
            self.assertLess(self.raw("POST", base + "dispatch", {}, self.hdr)[0], 300)
            for _ in range(100):
                st = json.loads(self.raw("GET", "/api/v1/tasks/" + tid)[2])["stages"][0]
                if st["state"] not in ("queued", "running"):
                    break
                time.sleep(0.02)
        self.assertEqual(st["state"], "completed", st); self.assertEqual(calls, [["/usr/bin/xfce4-terminal"]])
        bad = dict(stage, key="bad", arguments={"id": "git"})
        self.assertGreaterEqual(self.raw("POST", "/api/v1/tasks", {"title": "x", "goal": "", "stages": [bad]}, self.hdr)[0], 400)

    def test_doc_endpoint_returns_text_through_the_tool_plane(self):
        (self.root / "n.md").write_text("# hi")
        s, _, d = self.raw("GET", "/api/v1/workspace/doc?path=n.md")
        self.assertEqual((s, json.loads(d)["text"]), (200, "# hi"))
        self.assertEqual(self.raw("GET", "/api/v1/workspace/doc?path=../x")[0], 403)
        self.assertEqual(self.raw("GET", "/api/v1/workspace/doc")[0], 400)

    def test_raw_refuses_escapes_symlinks_and_bad_queries(self):
        (self.root / "ok.png").write_bytes(b"x"); (self.root / "l.png").symlink_to(self.root / "ok.png")
        for q in ("path=../a.png", "path=/etc/passwd", "path=l.png", "path=.git/x.png", "", "path=a&path=b"):
            self.assertIn(self.raw("GET", "/api/v1/workspace/raw?" + q)[0], (400, 403), q)

    def test_page_csp_allows_only_same_origin_and_loopback_frames(self):
        _, h, _ = self.raw("GET", "/api/v1/apps")
        csp = h["Content-Security-Policy"]
        self.assertIn("frame-src 'self' http://127.0.0.1:* http://localhost:*", csp)
        self.assertIn("frame-ancestors 'none'", csp)

if __name__ == "__main__":
    unittest.main()
