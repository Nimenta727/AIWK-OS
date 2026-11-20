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
