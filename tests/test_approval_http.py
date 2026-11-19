"""End-to-end HTTP workflow using a mocked official CLI (no real model calls)."""
import http.client
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from aiws.server import make_server


class ApprovalHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.calls = []
        def fake(task, project, brief):
            self.calls.append((task["id"], str(project)))
            return True, "verified mocked CLI execution"
        self.server = make_server(Path(self.temp.name), 0, allow_codex_readonly=True, executor=fake)
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)
        self.temp.cleanup()

    def req(self,method,path,body=None,token=None):
        conn = http.client.HTTPConnection("127.0.0.1",self.port,timeout=5)
        headers = {}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if token:
            headers["X-AIWS-Token"] = token
        conn.request(method,path,body=json.dumps(body) if body is not None else None,headers=headers)
        response=conn.getresponse()
        code=response.status
        content=json.loads(response.read())
        conn.close()
        return code,content

    def test_no_approval_no_execution_and_replay_rejected(self):
        _,session=self.req("GET","/api/session")
        token=session["csrf"]
        self.req("POST","/api/projects",{"name":"repo"},token)
        (self.server.store.project_path("repo") / ".git").mkdir()
        _,task=self.req("POST","/api/tasks",{"title":"inspect","description":"Review structure","project":"repo","agent":"codex"},token)
        task_id=task["task"]["id"]
        self.req("POST",f"/api/tasks/{task_id}/prepare",{},token)
        status,response=self.req("POST",f"/api/tasks/{task_id}/request-readonly",{},token)
        self.assertEqual(status,201)
        approval_id=response["approval"]["id"]
        time.sleep(0.1)
        self.assertEqual(self.calls,[])
        status,_=self.req("POST",f"/api/approvals/{approval_id}/decide",{"decision":"approve"})
        self.assertEqual(status,403)
        status,_=self.req("POST",f"/api/approvals/{approval_id}/decide",{"decision":"approve"},token)
        self.assertEqual(status,200)
        status,_=self.req("POST",f"/api/approvals/{approval_id}/decide",{"decision":"approve"},token)
        self.assertEqual(status,400)
        for _ in range(100):
            _,jobs=self.req("GET","/api/jobs")
            if jobs["jobs"] and jobs["jobs"][0]["status"]=="succeeded":
                break
            time.sleep(0.02)
        self.assertEqual(jobs["jobs"][0]["status"],"succeeded")
        self.assertEqual(len(self.calls),1)
        _,tasks=self.req("GET","/api/tasks")
        self.assertEqual(tasks["tasks"][0]["status"],"done")

if __name__ == "__main__":
    unittest.main()
