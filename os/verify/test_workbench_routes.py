"""The workbench HTTP route table is the whole attack surface of the guest UI service: hold it to that.

  * a path that is not in the table is 404 for GET and POST, and for POST before Origin/CSRF are even looked at
  * every POST route refuses a request without the CSRF header, a foreign Origin, and a non-JSON body
  * every API path the React UI calls is in the table (catches a UI/server drift in either direction)
  * the table has no duplicates and no pattern hidden behind an earlier one
"""
import http.client
import json
import os
import re
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
import aiws_workbench_http as H
from aiws_workbench import make_server, HOST


def concrete(segments):
    return "/" + "/".join("x1" if s.startswith("{") else s for s in segments)


class Table(unittest.TestCase):
    def test_no_duplicates_and_no_pattern_is_shadowed_by_an_earlier_one(self):
        for routes in (H.GET_ROUTES, H.POST_ROUTES):
            patterns = [segments for segments, _ in routes]
            self.assertEqual(len(patterns), len(set(patterns)))
            for segments, fn in routes:
                self.assertIs(H.match(routes, concrete(segments))[0], fn, segments)

    def test_matching_is_exact(self):
        fn, params = H.match(H.POST_ROUTES, "/api/v1/tasks/t1/stages/s2/approve")
        self.assertIs(fn, H.post_stage_approve)
        self.assertEqual(params, {"task": "t1", "stage": "s2"})
        for path in ("/api/v1/tasks/", "/api/v1/tasks//stages/s/approve", "/api/v1/tasks/t/stages/s/run",
                     "api/v1/jobs", "/api/v1/jobs/", "/api/v1/jobs/x", "//api/v1/jobs", "/api/v1/system/reboot",
                     "/api/v1/builder/runs/r/delete", "/api/v1/builder/mandates/m/approve", "/API/v1/jobs", ""):
            self.assertIsNone(H.match(H.POST_ROUTES, path)[0], path)
        self.assertIsNone(H.match(H.GET_ROUTES, "/api/v1/tasks/")[0])
        self.assertEqual(H.match(H.GET_ROUTES, "/api/v1/tasks/abc/audit")[1], {"task": "abc"})

    def test_every_api_path_the_ui_calls_is_routed(self):
        src = "".join(p.read_text(encoding="utf-8") for p in (ROOT.parent / "workbench/src").rglob("*.ts*"))
        # the UI calls api('/x/y'...) / fetch('/api/v1/x'): collect the literal part before any query or template
        literals = set(re.findall(r"""(?:api|get|post|apiGet|apiPost)(?:<[^>]*>)?\(\s*['"`](/[a-z][A-Za-z0-9/_-]*)""", src))
        literals |= {m[len("/api/v1"):] for m in re.findall(r"""['"`](/api/v1/[A-Za-z0-9/_-]+)""", src)}
        self.assertGreater(len(literals), 25, "the scan must find the UI's calls")
        missing = []
        for lit in sorted(literals):
            path = "/api/v1" + lit
            if path.endswith("/"):                   # a prefix the UI completes with an id, e.g. '/builder/runs/'+id+'/stop'
                prefix = tuple(path[1:-1].split("/"))
                ok = any(segments[:len(prefix)] == prefix and len(segments) > len(prefix)
                         for segments, _ in H.GET_ROUTES + H.POST_ROUTES)
            else:
                ok = H.match(H.GET_ROUTES, path)[0] is not None or H.match(H.POST_ROUTES, path)[0] is not None
            if not ok:
                missing.append(path)
        self.assertEqual(missing, [])


class StaticAssets(unittest.TestCase):
    """The UI's icon font is a .ttf (from @vscode/codicons). It was missing from ASSETS, so the service answered 404 and
    every icon in the shipped image was blank. Every file type the UI build can emit must be servable."""
    def test_every_font_and_asset_type_the_ui_uses_is_served(self):
        suffixes = set()
        dist = ROOT.parent / "workbench/dist/assets"
        if dist.is_dir():
            suffixes |= {p.suffix for p in dist.iterdir() if p.is_file()}
        css = ROOT.parent / "workbench/node_modules/@vscode/codicons/dist/codicon.css"
        if css.is_file():
            suffixes |= {"." + m for m in re.findall(r"url\([\"']?[^)\"'?#]+\.([a-z0-9]+)", css.read_text())}
        if not suffixes:
            self.skipTest("neither a built UI nor node_modules is present")
        self.assertIn(".ttf", suffixes)                              # the scan must see the icon font
        self.assertEqual(sorted(suffixes - set(H.ASSETS)), [])


class Server(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        root = base / "workspace"
        root.mkdir()
        ui = base / "ui"
        (ui / "assets").mkdir(parents=True)
        (ui / "index.html").write_text("<html><head></head><body></body></html>")
        self.patches = [patch.dict(os.environ, {"AIWS_WORKSPACE": str(root.resolve()), "XDG_STATE_HOME": str(base / "state"),
                                                "AIWS_SKILLS_DIR": str(base / "none")}),
                        patch("aiws_workbench.load_config", lambda: {"externalEnabled": False, "providers": {},
                                                                     "extraLocalKeywords": [], "extraExternalKeywords": []}),
                        patch("aiws_workbench.load_builder_config", lambda: {"enabled": False, "envAllow": [], "isolation": {
                            "mode": "none", "user": "x", "proxy": "http://127.0.0.1:3128"}})]
        for p in self.patches:
            p.start()
        self.server = make_server(root.resolve(), ui, 0)
        self.app = self.server.application
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.host = HOST + ":" + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.app.pool.shutdown(wait=True, cancel_futures=True)
        time.sleep(0.1)
        self.app.tasks.close()
        self.app.events.close()
        self.app.mandates.close()
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def request(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection(HOST, self.server.server_port, timeout=10)
        h = {"Host": self.host}
        h.update(headers or {})
        c.request(method, path, body=body, headers=h)
        r = c.getresponse()
        data = r.read()
        c.close()
        return r.status, (json.loads(data) if data[:1] == b"{" else data)

    def good(self, **extra):
        h = {"Content-Type": "application/json", "X-AIWS-CSRF": self.app.csrf, "Origin": "http://" + self.host}
        h.update(extra)
        return h

    def test_unlisted_paths_are_404_for_get_and_post_and_post_404_comes_before_csrf(self):
        for path in ("/api/v1/nope", "/api/v1/tasks/", "/api/v1/system/reboot", "/api/v1/builder/runs/x/delete",
                     "/api/v1/tasks/a/stages/b/run", "/api/v1/jobs/", "/api/v1/../v1/jobs", "/api/v2/jobs"):
            self.assertEqual(self.request("POST", path, b"{}", self.good())[0], 404, path)
            self.assertEqual(self.request("POST", path, b"{}", {"Content-Type": "application/json"})[0], 404, path)
        for path in ("/api/v1/nope", "/api/v1/tasks/", "/api/v1/jobs", "/api/v1/session/x", "/etc/passwd", "/assets/../index.html"):
            self.assertEqual(self.request("GET", path)[0], 404, path)

    def test_every_post_route_checks_origin_csrf_and_json_before_running(self):
        for segments, fn in H.POST_ROUTES:
            path = concrete(segments)
            with patch.object(self.app, "csrf", self.app.csrf):
                self.assertEqual(self.request("POST", path, b"{}", self.good(**{"X-AIWS-CSRF": "wrong"}))[0], 403, path)
                headers = self.good()
                del headers["X-AIWS-CSRF"]
                self.assertEqual(self.request("POST", path, b"{}", headers)[0], 403, path)
                self.assertEqual(self.request("POST", path, b"{}", self.good(Origin="http://evil.example"))[0], 403, path)
                self.assertEqual(self.request("POST", path, b"{}", self.good(**{"Content-Type": "text/plain"}))[0], 415, path)
                self.assertEqual(self.request("POST", path, b"", self.good())[0], 413, path)
                self.assertEqual(self.request("POST", path, b"[1]", self.good())[0], 400, path)

    def test_wrong_host_is_refused_for_both_methods(self):
        for method in ("GET", "POST"):
            self.assertEqual(self.request(method, "/api/v1/session", b"{}", {"Host": "evil.example:80"})[0], 403)

    def test_a_routed_get_and_post_still_work_end_to_end(self):
        status, body = self.request("GET", "/api/v1/session")
        self.assertEqual((status, body["csrf"]), (200, self.app.csrf))
        self.assertEqual(self.request("GET", "/api/v1/tasks/nope")[0], 404)
        status, body = self.request("POST", "/api/v1/model/disable", b"{\"x\":1}", self.good())
        self.assertEqual((status, body["error"]), (400, "Model toggle accepts no body fields"))


if __name__ == "__main__":
    unittest.main()
