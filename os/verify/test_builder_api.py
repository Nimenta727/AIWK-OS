"""O3 integration: builder endpoints and the observatory (budget, run approvals) with the SYNTHETIC fake CLI."""
import http.client
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
from aiws_workbench import make_server, HOST

FAKE = str(Path(__file__).resolve().parent / "fixtures" / "fake_cli.py")
GOOD = {"provider": "claude", "projectDir": "app", "allowedTools": ["Read", "Edit", "Bash(npm test)"], "permissionMode": "default",
        "maxTurns": 20, "tokenBudget": {"input": 100000, "output": 50000}, "wallClockMinutes": 5}

class BuilderApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.root = base / "workspace"; (self.root / "app").mkdir(parents=True)
        self.ui = base / "ui"; (self.ui / "assets").mkdir(parents=True)
        (self.ui / "index.html").write_text("<html><head></head><body></body></html>")
        self.env = patch.dict(os.environ, {"AIWS_WORKSPACE": str(self.root), "XDG_STATE_HOME": str(base / "state")})
        self.env.start()
        self.enabled = [True]
        self.scenario = ["ok"]
        self.cfgs = [patch("aiws_workbench.load_config", lambda: {"externalEnabled": False, "providers": {"claude": True, "codex": True},
                                                                  "extraLocalKeywords": [], "extraExternalKeywords": []}),
                     patch("aiws_workbench.load_builder_config", lambda: {"enabled": self.enabled[0], "envAllow": []})]
        [p.start() for p in self.cfgs]
        self.server = make_server(self.root, self.ui, 0)
        self.app = self.server.application
        self.app.supervisor.config = lambda: {"enabled": self.enabled[0], "envAllow": []}
        self.app.supervisor.launcher = lambda m, prompt, cwd: ([sys.executable, FAKE] + self.scenario, {})
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.hdr = {"X-AIWS-CSRF": self.req("GET", "/api/v1/session")[1]["csrf"]}

    def tearDown(self):
        run = self.app.supervisor.active
        if run is not None:
            self.app.supervisor._terminate(run); self.app.supervisor.wait(5)
        self.server.shutdown(); self.thread.join(timeout=3); self.server.server_close()
        self.app.pool.shutdown(wait=True, cancel_futures=True)
        time.sleep(0.2)
        self.app.tasks.close(); self.app.events.close(); self.app.mandates.close()
        [p.stop() for p in self.cfgs]; self.env.stop(); self.temp.cleanup()

    def req(self, method, path, payload=None, headers=None):
        conn = http.client.HTTPConnection(HOST, self.server.server_port, timeout=5)
        hdr = {"Host": HOST + ":" + str(self.server.server_port)}
        hdr.update(headers or {})
        if payload is not None:
            payload = json.dumps(payload); hdr["Content-Type"] = "application/json"
        conn.request(method, path, body=payload, headers=hdr)
        r = conn.getresponse(); body = json.loads(r.read()); conn.close()
        return r.status, body

    def post(self, path, payload=None):
        return self.req("POST", path, {} if payload is None else payload, self.hdr)

    def obs(self):
        return self.req("GET", "/api/v1/observatory")[1]

    def wait_idle(self):
        self.assertTrue(self.app.supervisor.wait(20))

    def grant(self, **over):
        status, m = self.post("/api/v1/builder/mandates", {**GOOD, **over})
        self.assertEqual(status, 202, m)
        return m

    def test_disabled_by_default_and_needs_csrf(self):
        self.enabled[0] = False
        status, b = self.req("GET", "/api/v1/builder")
        self.assertEqual((status, b["enabled"], b["mandates"]), (200, False, []))
        self.assertEqual(self.post("/api/v1/builder/mandates", GOOD)[0], 403)
        self.enabled[0] = True
        self.assertEqual(self.req("POST", "/api/v1/builder/mandates", GOOD)[0], 403)            # no CSRF token
        self.assertEqual(self.obs()["status"]["builder"]["state"], "idle")
        self.enabled[0] = False
        self.assertEqual(self.obs()["status"]["builder"]["state"], "disabled")

    def test_grant_validation_over_http_and_listing_without_secrets(self):
        for bad in ({**GOOD, "allowedTools": ["Bash"]}, {**GOOD, "projectDir": "../x"}, {**GOOD, "permissionMode": "bypassPermissions"},
                    {**GOOD, "unknown": 1}, {**GOOD, "needApprovalFor": ["delete"]}):
            status, out = self.post("/api/v1/builder/mandates", bad)
            self.assertEqual(status, 400, bad)
            self.assertIn("error", out)
        m = self.grant()
        b = self.req("GET", "/api/v1/builder")[1]
        self.assertEqual([x["id"] for x in b["mandates"]], [m["id"]])
        self.assertNotIn("sha256", b["mandates"][0])
        self.assertIn("claude", b["providers"])
        status, out = self.post("/api/v1/builder/mandates/" + m["id"] + "/revoke")
        self.assertEqual((status, out["state"]), (202, "revoked"))
        self.assertEqual(self.req("GET", "/api/v1/builder")[1]["mandates"], [])

    def test_run_budget_meter_and_session_in_observatory(self):
        self.assertIsNone(self.obs()["tokens"]["budget"])
        m = self.grant()
        s = self.obs()
        self.assertEqual((s["tokens"]["budget"]["used"], s["tokens"]["budget"]["limit"]), (0, 150000))
        status, started = self.post("/api/v1/builder/runs", {"mandateId": m["id"], "prompt": "build the app"})
        self.assertEqual(status, 202, started)
        self.wait_idle()
        s = self.obs()
        self.assertEqual(s["tokens"]["budget"]["used"], 250 + 60)                  # provider-reported total of the finished run
        self.assertEqual(s["status"]["builder"]["state"], "idle")
        build = next(x for x in s["sessions"] if x["session"].startswith("build-"))
        self.assertEqual((build["agent"], build["tokens"]["in"]), ("claude", 250))
        self.assertEqual(self.post("/api/v1/builder/runs", {"mandateId": m["id"]})[0], 400)     # prompt required

    def test_live_budget_while_running_and_stop(self):
        m = self.grant()
        self.scenario = ["hang"]
        self.post("/api/v1/builder/runs", {"mandateId": m["id"], "prompt": "x"})
        for _ in range(60):
            if self.obs()["status"]["builder"]["state"] == "running":
                break
            time.sleep(0.05)
        s = self.obs()
        self.assertEqual(s["status"]["builder"]["state"], "running")
        self.assertEqual(self.post("/api/v1/builder/runs", {"mandateId": m["id"], "prompt": "y"})[0], 409)   # one at a time
        rid = s["status"]["builder"]["runId"]
        self.assertEqual(self.post("/api/v1/builder/runs/" + rid + "/stop")[0], 202)
        self.wait_idle()
        self.assertEqual(self.obs()["status"]["builder"]["state"], "idle")
        self.assertEqual(self.post("/api/v1/builder/runs/" + rid + "/stop")[0], 409)
        self.assertEqual(self.post("/api/v1/builder/runs/" + rid + "/stop", {"x": 1})[0], 400)

    def test_run_approval_appears_in_the_inbox_and_resumes(self):
        m = self.grant()
        self.scenario = ["tool", "Bash|git push origin main"]
        self.post("/api/v1/builder/runs", {"mandateId": m["id"], "prompt": "x"})
        s = None
        for _ in range(100):
            s = self.obs()
            if s["runApprovals"]:
                break
            time.sleep(0.05)
        self.assertEqual([a["category"] for a in s["runApprovals"]], ["git-push"])
        self.assertEqual(s["verdict"]["level"], "yellow")
        self.assertEqual(s["status"]["builder"]["state"], "awaiting-approval")
        rid = s["runApprovals"][0]["runId"]
        self.assertEqual(self.post("/api/v1/builder/runs/" + rid + "/approve")[0], 202)
        self.wait_idle()
        self.assertEqual(self.obs()["runApprovals"], [])
        self.assertEqual(self.req("GET", "/api/v1/builder")[1]["status"]["runs"][0]["state"], "completed")

    def test_denied_run_is_killed_and_budget_exhaustion_blocks_restart(self):
        m = self.grant(tokenBudget={"input": 2500, "output": 50000})
        self.scenario = ["overbudget"]
        self.post("/api/v1/builder/runs", {"mandateId": m["id"], "prompt": "x"})
        self.wait_idle()
        self.assertEqual(self.req("GET", "/api/v1/builder")[1]["status"]["runs"][0]["reason"], "token-budget")
        status, out = self.post("/api/v1/builder/runs", {"mandateId": m["id"], "prompt": "again"})
        self.assertEqual(status, 403)
        self.assertIn("used up", out["error"])

    def test_unknown_ids_and_bad_routes(self):
        self.assertEqual(self.post("/api/v1/builder/runs", {"mandateId": "nope", "prompt": "x"})[0], 400)
        self.assertEqual(self.post("/api/v1/builder/mandates/nope/revoke")[0], 400)
        self.assertEqual(self.post("/api/v1/builder/runs/nope/approve")[0], 409)
        self.assertEqual(self.post("/api/v1/builder/runs/abc/explode")[0], 404)

if __name__ == "__main__":
    unittest.main()
