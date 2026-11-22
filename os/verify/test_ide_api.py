"""Workbench endpoints for AIWS Code: status and a fixed-command launch. A FAKE launcher script is used."""
import http.client
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
from aiws_workbench import make_server, HOST

FAKE_LAUNCHER = """#!/bin/sh
{ echo "ARGS:$#"; env | sort; } > "%s"
"""

class IdeApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.root = base / "workspace"; self.root.mkdir()
        self.ui = base / "ui"; (self.ui / "assets").mkdir(parents=True); (self.ui / "index.html").write_text("<html><head></head><body></body></html>")
        self.ide = base / "aiws-code"; (self.ide / "bin").mkdir(parents=True); (self.ide / "out").mkdir()
        self.out = base / "launch.out"
        self.launcher = base / "launcher"; self.launcher.write_text(FAKE_LAUNCHER % self.out); self.launcher.chmod(0o755)
        s = socket.socket(); s.bind(("127.0.0.1", 0)); self.port = s.getsockname()[1]; s.close()
        self.env = patch.dict(os.environ, {"AIWS_WORKSPACE": str(self.root), "XDG_STATE_HOME": str(base / "state"), "AIWS_CODE_ROOT": str(self.ide),
                                           "AIWS_CODE_PORT": str(self.port), "SECRET_TOKEN": "must-not-leak"})
        self.env.start()
        self.cfgs = [patch("aiws_workbench.load_config", lambda: {"externalEnabled": False, "providers": {}, "extraLocalKeywords": [], "extraExternalKeywords": []}),
                     patch("aiws_workbench.load_builder_config", lambda: {"enabled": False, "envAllow": [], "isolation": {"mode": "none", "user": "x", "proxy": "http://127.0.0.1:3128"}})]
        [p.start() for p in self.cfgs]
        self.server = make_server(self.root, self.ui, 0)
        self.server.application.ide_launcher = str(self.launcher)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.hdr = {"X-AIWS-CSRF": self.req("GET", "/api/v1/session")[1]["csrf"]}

    def tearDown(self):
        self.server.shutdown(); self.server.server_close()
        self.server.application.pool.shutdown(wait=True, cancel_futures=True)
        time.sleep(0.2)
        a = self.server.application; a.tasks.close(); a.events.close(); a.mandates.close()
        [p.stop() for p in self.cfgs]; self.env.stop(); self.temp.cleanup()

    def req(self, method, path, payload=None, headers=None):
        c = http.client.HTTPConnection(HOST, self.server.server_port, timeout=10)
        h = {"Host": HOST + ":" + str(self.server.server_port), **(headers or {})}
        if payload is not None:
            payload = json.dumps(payload); h["Content-Type"] = "application/json"
        c.request(method, path, body=payload, headers=h); r = c.getresponse(); b = json.loads(r.read()); c.close()
        return r.status, b

    def install(self):
        (self.ide / "bin/aiws-code-server").write_text("x"); (self.ide / "out/server-main.js").write_text("x")
        (self.ide / "PROVENANCE.json").write_text(json.dumps({"upstreamTag": "1.147.0"}))

    def test_status_reflects_installation_and_version(self):
        s = self.req("GET", "/api/v1/ide")[1]
        self.assertEqual((s["installed"], s["running"], s["launcherPresent"], s["version"], s["port"]), (False, False, True, None, self.port))
        self.install()
        s = self.req("GET", "/api/v1/ide")[1]
        self.assertEqual((s["installed"], s["version"]), (True, "1.147.0"))

    def test_open_refuses_when_not_installed(self):
        status, out = self.req("POST", "/api/v1/ide/open", {}, self.hdr)
        self.assertEqual(status, 409)
        self.assertIn("not installed", out["error"])
        self.assertFalse(self.out.exists())

    def test_open_launches_the_fixed_command_with_a_filtered_environment(self):
        self.install()
        status, out = self.req("POST", "/api/v1/ide/open", {}, self.hdr)
        self.assertEqual((status, out["started"]), (202, True))
        for _ in range(60):
            if self.out.exists() and "AIWS_WORKSPACE=" in self.out.read_text():   # the script writes the line last
                break
            time.sleep(0.05)
        text = self.out.read_text()
        self.assertIn("ARGS:0", text)                                         # no argument ever comes from the request
        self.assertIn("AIWS_WORKSPACE=" + str(self.root), text)
        self.assertNotIn("SECRET_TOKEN", text)                                # the environment is an allowlist
        self.assertEqual(self.req("POST", "/api/v1/ide/open", {}, self.hdr)[1].get("starting"), True)   # rate limited: no spawn storm

    def test_already_running_is_not_started_again(self):
        self.install()
        l = socket.socket(); l.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); l.bind(("127.0.0.1", self.port)); l.listen(2)
        try:
            self.assertTrue(self.req("GET", "/api/v1/ide")[1]["running"])
            status, out = self.req("POST", "/api/v1/ide/open", {}, self.hdr)
            self.assertEqual((status, out["started"], out["running"]), (202, False, True))
            time.sleep(0.2)
            self.assertFalse(self.out.exists())
        finally:
            l.close()

    def test_csrf_and_arguments_are_enforced(self):
        self.install()
        self.assertEqual(self.req("POST", "/api/v1/ide/open", {})[0], 403)
        self.assertEqual(self.req("POST", "/api/v1/ide/open", {"folder": "/etc"}, self.hdr)[0], 400)
        self.assertFalse(self.out.exists())


class IdeSessionTests(IdeApiTests):
    """The tab embedded in the workbench: server-only start and a CSRF-protected session URL."""
    TOKEN = "0123456789abcdef0123456789abcdef"
    def setUp(self):
        super().setUp(); self.rt = Path(self.temp.name) / "run"; self.rt.mkdir(mode=0o700)
        self.rt_env = patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(self.rt)}); self.rt_env.start(); self.listener = None
        (self.root / "proj").mkdir()
    def tearDown(self):
        self.rt_env.stop()
        if self.listener: self.listener.close()
        super().tearDown()
    def token(self, text=None, mode=0o600):
        f = self.rt / "aiws-code.token"; f.write_text(self.TOKEN if text is None else text); f.chmod(mode); return f
    def running(self):
        self.listener = socket.socket(); self.listener.bind(("127.0.0.1", self.port)); self.listener.listen(4)
    def test_start_runs_the_launcher_in_server_only_mode(self):
        self.install(); s, b = self.req("POST", "/api/v1/ide/start", {}, self.hdr); self.assertEqual((s, b["started"]), (202, True)); time.sleep(0.5)
        self.assertIn("ARGS:1", self.out.read_text()); self.assertNotIn("must-not-leak", self.out.read_text())
        self.assertEqual(self.req("POST", "/api/v1/ide/start", {"folder": "x"}, self.hdr)[0], 400); self.assertEqual(self.req("POST", "/api/v1/ide/start", {})[0], 403)
    def test_session_needs_install_running_and_a_safe_token(self):
        self.token(); self.assertGreaterEqual(self.req("POST", "/api/v1/ide/session", {}, self.hdr)[0], 400)           # not installed
        self.install(); self.assertGreaterEqual(self.req("POST", "/api/v1/ide/session", {}, self.hdr)[0], 400)         # not running
    def test_session_url_has_token_and_a_confined_absolute_folder(self):
        self.install(); self.running(); self.token()
        s, b = self.req("POST", "/api/v1/ide/session", {"path": "proj"}, self.hdr); self.assertEqual(s, 202, b)
        self.assertTrue(b["url"].startswith("http://127.0.0.1:%d/?tkn=%s&folder=" % (self.port, self.TOKEN))); self.assertEqual(b["folder"], str((self.root / "proj").resolve())); self.assertIn("%", b["url"].replace("%2F", "")) if " " in b["folder"] else None
        s, b = self.req("POST", "/api/v1/ide/session", {}, self.hdr); self.assertEqual(b["folder"], str(self.root.resolve()))
    def test_folder_must_stay_inside_the_workspace(self):
        self.install(); self.running(); self.token()
        for bad in ("..", "../x", "/etc", ".git", "proj/../../x", 5):
            s, b = self.req("POST", "/api/v1/ide/session", {"path": bad}, self.hdr); self.assertGreaterEqual(s, 400, bad); self.assertNotIn("url", b)
        self.assertEqual(self.req("POST", "/api/v1/ide/session", {"path": "proj", "extra": 1}, self.hdr)[0], 400)
        self.assertEqual(self.req("POST", "/api/v1/ide/session", {"path": "proj"})[0], 403)
    def test_unsafe_token_files_are_refused_and_never_echoed(self):
        self.install(); self.running()
        for text, mode in ((None, 0o644), ("not hex!", 0o600), ("abc", 0o600), ("0" * 300, 0o600), ("", 0o600)):
            self.token(text, mode); s, b = self.req("POST", "/api/v1/ide/session", {}, self.hdr); self.assertGreaterEqual(s, 400, (text, mode)); self.assertNotIn(self.TOKEN, json.dumps(b))
        (self.rt / "aiws-code.token").unlink(); self.assertGreaterEqual(self.req("POST", "/api/v1/ide/session", {}, self.hdr)[0], 400)
        real = self.rt / "real"; real.write_text(self.TOKEN); real.chmod(0o600); (self.rt / "aiws-code.token").symlink_to(real)
        self.assertGreaterEqual(self.req("POST", "/api/v1/ide/session", {}, self.hdr)[0], 400)                     # a symlink is refused
    def test_the_token_is_not_in_the_get_status(self):
        self.install(); self.running(); self.token(); s, b = self.req("GET", "/api/v1/ide"); self.assertNotIn(self.TOKEN, json.dumps(b))

if __name__ == "__main__":
    unittest.main()
