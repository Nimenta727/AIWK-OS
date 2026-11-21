"""Offline integration tests for guest-local workbench service and tool queue."""
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))
from aiws_workbench import make_server, HOST

class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.root = base / "workspace"
        self.root.mkdir()
        self.ui = base / "ui"
        (self.ui / "assets").mkdir(parents=True)
        (self.ui / "index.html").write_text("<html><head></head><body></body></html>")
        (self.ui / "assets/main.js").write_text("console.log('test');")
        (self.root / "Example.cs").write_text("public class Example {}")
        self.env = patch.dict(os.environ, {"AIWS_WORKSPACE": str(self.root),
                                           "XDG_STATE_HOME": str(base / "state")})
        self.env.start()
        self.server = make_server(self.root, self.ui, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=3)
        self.server.server_close()
        self.server.application.pool.shutdown(wait=True, cancel_futures=True)
        self.server.application.tasks.close()
        self.env.stop()
        self.temp.cleanup()

    def request(self, method, path, payload=None, headers=None):
        conn = http.client.HTTPConnection(HOST, self.server.server_port, timeout=3)
        hdr = {"Host": HOST + ":" + str(self.server.server_port)}
        hdr.update(headers or {})
        if payload is not None:
            payload = json.dumps(payload)
            hdr["Content-Type"] = "application/json"
        conn.request(method, path, body=payload, headers=hdr)
        response = conn.getresponse()
        raw = response.read()
        body = json.loads(raw) if response.getheader("Content-Type", "").startswith("application/json") else raw
        status = response.status
        conn.close()
        return status, body

    def test_health_html_and_host_guard(self):
        status, health = self.request("GET", "/api/v1/health")
        self.assertEqual(status, 200)
        self.assertTrue(health["guestOnly"])
        self.assertFalse(health["agentPrivileged"])
        status, html = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"os-bridge.js", html)
        self.assertEqual(self.request("GET", "/assets/main.js")[0], 200)
        self.assertEqual(self.request("GET", "/../../etc/passwd")[0], 404)
        self.assertEqual(self.request("GET", "/api/v1/health", headers={"Host": "attacker.invalid"})[0], 403)

    def test_csrf_origin_and_read_only_enforcement(self):
        csrf = self.request("GET", "/api/v1/session")[1]["csrf"]
        data = {"tool": "code.symbols", "arguments": {"query": "Example"}}
        self.assertEqual(self.request("POST", "/api/v1/jobs", data)[0], 403)
        h = {"X-AIWS-CSRF": csrf, "Origin": "https://attacker.invalid"}
        self.assertEqual(self.request("POST", "/api/v1/jobs", data, h)[0], 403)
        h = {"X-AIWS-CSRF": csrf}
        for blocked in ("runtime.test", "project.scaffold", "browser.snapshot"):
            self.assertEqual(self.request("POST", "/api/v1/jobs",
                                          {"tool": blocked, "arguments": {}}, h)[0], 400)
        self.assertEqual(self.request("POST", "/api/v1/jobs", data, h)[0], 202)

    def test_guest_files_listing_read_and_sha_write(self):
        import hashlib
        status, tree = self.request("GET", "/api/v1/workspace/tree")
        self.assertEqual(status, 200)
        self.assertIn("Example.cs", tree["files"])
        status, file = self.request("GET", "/api/v1/workspace/file?path=Example.cs")
        self.assertEqual(status, 200)
        self.assertEqual(file["text"], "public class Example {}")
        self.assertEqual(self.request("GET", "/api/v1/workspace/file?path=%2Fetc%2Fpasswd")[0], 403)
        csrf = self.request("GET", "/api/v1/session")[1]["csrf"]
        text = "public class GuestOnly {}"
        _, job = self.request("POST", "/api/v1/jobs", {"tool": "file.replace",
             "arguments": {"path": "Example.cs", "text": text,
                           "expectedSha256": file["sha256"]}}, {"X-AIWS-CSRF": csrf})
        result = {}
        for _ in range(100):
            _, result = self.request("GET", "/api/v1/jobs/" + job["id"])
            if result["status"] not in ("queued", "running"):
                break
            time.sleep(0.01)
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual((self.root / "Example.cs").read_text(), text)
        self.assertEqual(self.request("GET", "/api/v1/workspace/file?path=Example.cs")[1]["sha256"],
                         hashlib.sha256(text.encode()).hexdigest())
        _, stale = self.request("POST", "/api/v1/jobs", {"tool": "file.replace",
             "arguments": {"path": "Example.cs", "text": "unauthorized collision",
                           "expectedSha256": file["sha256"]}}, {"X-AIWS-CSRF": csrf})
        for _ in range(100):
            _, result = self.request("GET", "/api/v1/jobs/" + stale["id"])
            if result["status"] not in ("queued", "running"):
                break
            time.sleep(0.01)
        self.assertEqual(result["status"], "failed", result)
        self.assertEqual((self.root / "Example.cs").read_text(), text)

    def test_local_model_lifecycle_cannot_manage_host(self):
        token=self.request("GET","/api/v1/session")[1]["csrf"]
        self.assertEqual(self.request("POST","/api/v1/model/enable",{})[0],403)
        hdr={"X-AIWS-CSRF":token}
        status,response=self.request("POST","/api/v1/model/enable",{},hdr)
        self.assertEqual(status,403,response)
        self.assertIn("AIWS",response["error"])
        status,response=self.request("POST","/api/v1/model/disable",{},hdr)
        self.assertEqual(status,403,response)
        self.assertFalse(self.request("GET","/api/v1/model/status")[1]["online"])

    def test_persistent_task_dag_and_disabled_offline_model(self):
        self.assertFalse(self.request("GET", "/api/v1/model/status")[1]["configured"])
        token = self.request("GET", "/api/v1/session")[1]["csrf"]
        hdr = {"X-AIWS-CSRF": token}
        stage = {"key": "inspect", "label": "Inspect guest workspace",
                 "tool": "workspace.tree", "arguments": {"path": "."}, "dependsOn": []}
        status, task = self.request("POST", "/api/v1/tasks",
                                    {"title": "Guest inventory", "goal": "Inspect",
                                     "stages": [stage]}, hdr)
        self.assertEqual(status, 202)
        taskid = task["task"]["id"]
        self.assertEqual(self.request("GET", "/api/v1/tasks")[1]["tasks"][0]["id"], taskid)
        self.assertEqual(self.request("POST", "/api/v1/tasks/" + taskid +
                                      "/stages/inspect/dispatch", {}, hdr)[0], 202)
        value = None
        for _ in range(100):
            _, value = self.request("GET", "/api/v1/tasks/" + taskid)
            if value["stages"][0]["state"] not in ("queued", "running"):
                break
            time.sleep(0.01)
        self.assertEqual(value["stages"][0]["state"], "completed", value)
        self.assertGreaterEqual(len(self.request("GET", "/api/v1/tasks/" +
                                                taskid + "/audit")[1]["events"]), 3)
        self.assertEqual(self.request("POST", "/api/v1/model/suggest",
                                      {"instruction": "list guest files"}, hdr)[0], 400)
        self.assertEqual(self.request("POST", "/api/v1/tasks/" + taskid +
                                      "/stages/inspect/dispatch", {}, hdr)[0], 400)

    def test_guest_service_and_kernel_dag_are_approval_gated(self):
        csrf = self.request("GET","/api/v1/session")[1]["csrf"]
        hdr = {"X-AIWS-CSRF": csrf}
        dangerous = {"key":"service","label":"Restart guest model",
            "tool":"service.restart","arguments":{"service":"aiws-local-model.service"},"dependsOn":[]}
        status,task=self.request("POST","/api/v1/tasks",
            {"title":"Guest model restart","goal":"","stages":[dangerous]},hdr)
        self.assertEqual(status,202,task)
        taskid=task["task"]["id"]
        uri="/api/v1/tasks/"+taskid+"/stages/service/"
        self.assertEqual(self.request("POST",uri+"dispatch",{},hdr)[0],400)
        self.assertEqual(self.request("POST",uri+"approve",{},hdr)[0],202)
        # Standalone unit tests are deliberately not dedicated VMs.
        # Guest-only operations cannot be exercised against this host.
        self.assertEqual(self.request("GET","/api/v1/guest/services")[0],403)
        self.assertEqual(self.request("GET","/api/v1/guest/kernel")[0],403)
        invalid={"key":"bad","label":"Host","tool":"service.restart",
                 "arguments":{"service":"sshd.service"},"dependsOn":[]}
        self.assertEqual(self.request("POST","/api/v1/tasks",
            {"title":"Unsafe plan","goal":"","stages":[invalid]},hdr)[0],400)

    def test_approved_kernel_stage_routes_through_guest_ops(self):
        token=self.request("GET","/api/v1/session")[1]["csrf"]
        hdr={"X-AIWS-CSRF":token}
        stage={"key":"kernel","label":"Guest candidate","tool":"kernel.stage",
               "arguments":{"path":"candidate.fragment","expectedSha256":"a"*64},
               "dependsOn":[]}
        status,doc=self.request("POST","/api/v1/tasks",
            {"title":"Kernel dispatch regression","goal":"","stages":[stage]},hdr)
        self.assertEqual(status,202,doc)
        tid=doc["task"]["id"]
        uri="/api/v1/tasks/"+tid+"/stages/kernel/"
        self.assertEqual(self.request("POST",uri+"dispatch",{},hdr)[0],400)
        self.assertEqual(self.request("POST",uri+"approve",{},hdr)[0],202)
        with patch.object(self.server.application.guest_ops,"execute",
             return_value={"deployed":False,"status":"staged","id":"test"} ) as runner:
            self.assertEqual(self.request("POST",uri+"dispatch",{},hdr)[0],202)
            result=None
            for _ in range(150):
                _,result=self.request("GET","/api/v1/tasks/"+tid)
                if result["stages"][0]["state"] not in ("queued","running"):
                    break
                time.sleep(.01)
        self.assertEqual(result["stages"][0]["state"],"completed",result)
        self.assertIs(result["stages"][0]["result"]["deployed"],False)
        runner.assert_called_once_with("kernel.stage",
            {"path":"candidate.fragment","expectedSha256":"a"*64},approved=True)

    def test_guest_service_in_dag_denied_without_vm_marker(self):
        token=self.request("GET","/api/v1/session")[1]["csrf"]
        hdr={"X-AIWS-CSRF":token}
        stage={"key":"inspect","label":"User service","tool":"service.inspect",
               "arguments":{"service":"aiws-workbench.service"},"dependsOn":[]}
        status,doc=self.request("POST","/api/v1/tasks",
            {"title":"Guest service guard","goal":"","stages":[stage]},hdr)
        self.assertEqual(status,202,doc)
        tid=doc["task"]["id"]
        self.assertEqual(self.request("POST","/api/v1/tasks/"+tid+
            "/stages/inspect/dispatch",{},hdr)[0],202)
        result=None
        for _ in range(150):
            _,result=self.request("GET","/api/v1/tasks/"+tid)
            if result["stages"][0]["state"] not in ("queued","running"):
                break
            time.sleep(.01)
        self.assertEqual(result["stages"][0]["state"],"failed",result)
        self.assertIn("guest image marker",result["stages"][0]["error"].lower())

    def test_local_model_proposal_becomes_pending_audited_task(self):
        csrf=self.request("GET","/api/v1/session")[1]["csrf"]
        hdr={"X-AIWS-CSRF":csrf}
        proposal={"tool":"workspace.tree","arguments":{"path":"."},
                  "reason":"Inspect guest files","requiresReview":True,
                  "executed":False,"source":"local-model"}
        with patch.object(self.server.application.model,"suggest",return_value=proposal):
            status,task=self.request("POST","/api/v1/model/plan",
                {"instruction":"List guest project files"},hdr)
        self.assertEqual(status,202,task)
        self.assertEqual(task["stages"][0]["state"],"pending")
        self.assertEqual(task["stages"][0]["tool"],"workspace.tree")
        events=self.request("GET","/api/v1/tasks/"+task["task"]["id"]+"/audit")[1]["events"]
        self.assertIn("model.proposed",[e["action"] for e in events])
        self.assertNotIn("List guest project files",json.dumps(events))

    def test_async_result(self):
        csrf = self.request("GET", "/api/v1/session")[1]["csrf"]
        _, job = self.request("POST", "/api/v1/jobs",
                              {"tool": "code.symbols", "arguments": {"query": "Example"}},
                              {"X-AIWS-CSRF": csrf})
        result = None
        for _ in range(100):
            _, result = self.request("GET", "/api/v1/jobs/" + job["id"])
            if result["status"] not in ("queued", "running"):
                break
            time.sleep(0.01)
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(result["result"]["count"], 1)
        self.assertFalse(result["result"]["semanticVerified"])
        self.assertEqual(self.request("GET", "/api/v1/jobs/not-a-job")[0], 404)

if __name__ == "__main__":
    unittest.main()
