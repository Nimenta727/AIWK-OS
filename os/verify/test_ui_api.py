"""HTTP layer for the plan panel and the sub-agent tree: real server, real stores, synthetic events."""
import http.client, json, os, sys, tempfile, threading, time, unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
import aiws_plans as P
import aiws_events as E
from aiws_workbench import make_server, HOST

class Api(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); base = Path(self.temp.name)
        self.root = (base / "workspace"); self.root.mkdir(); self.root = self.root.resolve()
        ui = base / "ui"; (ui / "assets").mkdir(parents=True); (ui / "index.html").write_text("<html><head></head><body></body></html>")
        self.env = patch.dict(os.environ, {"AIWS_WORKSPACE": str(self.root), "XDG_STATE_HOME": str(base / "state"), "AIWS_SKILLS_DIR": str(base / "none")}); self.env.start()
        self.cfgs = [patch("aiws_workbench.load_config", lambda: {"externalEnabled": False, "providers": {}, "extraLocalKeywords": [], "extraExternalKeywords": []}),
                     patch("aiws_workbench.load_builder_config", lambda: {"enabled": False, "envAllow": [], "isolation": {"mode": "none", "user": "x", "proxy": "http://127.0.0.1:3128"}})]
        [p.start() for p in self.cfgs]
        self.server = make_server(self.root, ui, 0); self.app = self.server.application
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
    def tearDown(self):
        self.server.shutdown(); self.server.server_close()
        self.app.pool.shutdown(wait=True, cancel_futures=True); time.sleep(0.2)
        self.app.tasks.close(); self.app.events.close(); self.app.mandates.close()
        [p.stop() for p in self.cfgs]; self.env.stop(); self.temp.cleanup()
    def get(self, path):
        c = http.client.HTTPConnection(HOST, self.server.server_port, timeout=10)
        c.request("GET", path, headers={"Host": HOST + ":" + str(self.server.server_port)}); r = c.getresponse(); d = r.read(); c.close()
        return r.status, json.loads(d)

    def test_plans_lists_cloud_plans_with_structure(self):
        self.app.plans.upsert(P.from_cloud("run1", "text", "Goal here\n1. Read code\n2. Delete the old table"))
        status, body = self.get("/api/v1/plans")
        self.assertEqual(status, 200)
        plan = next(p for p in body["plans"] if p["source"] == "cloud")
        self.assertEqual([s["title"] for s in plan["steps"]], ["Read code", "Delete the old table"]); self.assertIn("delete", plan["steps"][1]["hints"])
        self.assertTrue(plan["parsedFromText"])
    def test_plans_includes_local_task_plans_with_platform_risk(self):
        self.app.tasks.create("Tidy", "g", [{"key": "a", "label": "List", "tool": "workspace.tree", "arguments": {}, "dependsOn": []},
                                            {"key": "b", "label": "Trash old", "tool": "file.trash", "arguments": {"path": "old", "expectedSha256": "0" * 64}, "dependsOn": ["a"]}])
        _, body = self.get("/api/v1/plans")
        local = next(p for p in body["plans"] if p["source"] == "local"); risks = {s["id"]: s["risk"] for s in local["steps"]}
        self.assertEqual(risks, {"a": "low", "b": "high"})
    def test_tree_endpoint_builds_from_stored_events_and_validates_session(self):
        for i, kw in enumerate([dict(kind="start", detail="main-model"), dict(kind="tool", tool="Task", status="pending", node="toolu_A", parent="root", label="Audit"),
                                dict(kind="tool", tool="Read", status="pending", node="toolu_A", ctx=[{"kind": "file", "ref": "a.py"}]),
                                dict(kind="tool", tool="Task", status="ok", node="toolu_A")]):
            self.app.events.append(E.make_event(1000 + i, "claude", "run-1", **kw))
        status, body = self.get("/api/v1/observatory/tree?session=run-1")
        self.assertEqual(status, 200); by = {n["id"]: n for n in body["nodes"]}
        self.assertEqual((by["toolu_A"]["parent"], by["toolu_A"]["state"], by["toolu_A"]["model"]), ("root", "done", "main-model"))
        self.assertTrue(by["toolu_A"]["modelInherited"]); self.assertEqual(by["toolu_A"]["ctx"], [{"kind": "file", "ref": "a.py"}])
        for bad in ("../x", "a b", ""):
            self.assertEqual(self.get("/api/v1/observatory/tree?session=" + bad.replace(" ", "%20"))[0], 400, bad)
        self.assertEqual(self.get("/api/v1/observatory/tree?session=unknown")[1]["count"], 1)   # unknown session: just the root

class HealthFlags(Api):
    def test_health_reports_system_verify_and_work_disk(self):
        import aiws_sysverify
        self.assertIsNone(self.get("/api/v1/health")[1]["systemVerify"] if not os.path.exists(aiws_sysverify.RESULT) else None)
        result = Path(self.temp.name) / "verify.json"
        result.write_text(json.dumps({"ok": False, "modified": ["/usr/local/lib/aiws/x.py"], "missing": [], "unlisted": ["y" * 500]}))
        with patch.object(aiws_sysverify, "RESULT", str(result)):
            v = self.get("/api/v1/health")[1]["systemVerify"]
        self.assertFalse(v["ok"]); self.assertEqual(v["modified"], ["/usr/local/lib/aiws/x.py"]); self.assertEqual(len(v["unlisted"][0]), 200)
        result.write_text("not json")
        with patch.object(aiws_sysverify, "RESULT", str(result)):
            self.assertIsNone(self.get("/api/v1/health")[1]["systemVerify"])
        self.assertIn("workDisk", self.get("/api/v1/health")[1])

if __name__ == "__main__":
    unittest.main()
