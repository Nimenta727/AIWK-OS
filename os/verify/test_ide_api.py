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

if __name__ == "__main__":
    unittest.main()
