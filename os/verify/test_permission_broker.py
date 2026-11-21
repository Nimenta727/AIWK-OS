"""Independent same-UID policy decision tests, never real host/tool execution."""
import hashlib
import os
from pathlib import Path
import socket
import sqlite3
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))
from aiws_tasks import GuestTaskStore
from aiws_permission_broker import (
    BrokerClient, BrokerDenied, BrokerPolicy, MAX_TASK_WRITES,
    MAX_RECENT_WRITES, serve,
)

@unittest.skipUnless(os.name == "posix" and hasattr(socket, "SO_PEERCRED"),
                     "AF_UNIX peer credentials needed")
class PermissionBrokerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.state = self.root / "aiws"
        self.store = GuestTaskStore(self.state)
        self.policy = BrokerPolicy(self.state / "tasks.sqlite3",
                                   self.state / "broker-decisions.sqlite3")

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    @staticmethod
    def stage(tool="file.replace", key="write"):
        return {"key": key, "label": "Safe fixture", "tool": tool,
                "arguments": {"path": "project.txt", "text": "new",
                              "expectedSha256": "f" * 64}
                if tool == "file.replace" else {"path": "."},
                "dependsOn": []}

    def req(self, task_id, stage, args=None):
        return {"op": "authorize_stage", "taskId": task_id,
                "stageKey": stage["key"], "tool": stage["tool"],
                "arguments": stage["arguments"] if args is None else args}

    def test_direct_reads_and_all_direct_writes_are_separate(self):
        self.assertTrue(self.policy.decide(
            {"op": "authorize_read", "tool": "workspace.tree",
             "arguments": {"path": "."}})["allowed"])
        self.assertFalse(self.policy.decide(
            {"op": "authorize_read", "tool": "file.replace",
             "arguments": self.stage()["arguments"]})["allowed"])
        self.assertFalse(self.policy.decide(
            {"op": "authorize_read", "tool": "host.exec", "arguments": {}})["allowed"])
        self.assertFalse(self.policy.decide(
            {"op": "authorize_read", "tool": "file.read",
             "arguments": {"path": ".", "command": "rm -rf /"}})["allowed"])
        self.assertFalse(self.policy.decide(
            {"op": "authorize_read", "tool": "service.restart",
             "arguments": {"service": "aiws-local-model.service"}})["allowed"])

    def test_persisted_approval_running_state_argument_binding_and_replay(self):
        stage = self.stage()
        doc = self.store.create("replace", "", [stage])
        tid = doc["task"]["id"]
        request = self.req(tid, stage)
        self.assertFalse(self.policy.decide(request)["allowed"])
        self.store.approve(tid, "write")
        self.assertFalse(self.policy.decide(request)["allowed"])
        self.store.dispatch(tid, "write")
        self.assertFalse(self.policy.decide(request)["allowed"])
        self.store.started(tid, "write")
        changed = dict(stage["arguments"])
        changed["text"] = "other content"
        self.assertFalse(self.policy.decide(self.req(tid, stage, changed))["allowed"])
        self.assertTrue(self.policy.decide(request)["allowed"])
        self.assertFalse(self.policy.decide(request)["allowed"])
        self.store.finished(tid, "write", result={"ok": True})
        self.assertFalse(self.policy.decide(request)["allowed"])
        with sqlite3.connect(self.state / "broker-decisions.sqlite3") as conn:
            row = conn.execute("SELECT count(*) FROM granted").fetchone()[0]
        self.assertEqual(row, 1)

    def test_read_only_dag_is_authorized_only_when_running(self):
        stage = self.stage("workspace.tree", "inspect")
        doc = self.store.create("read", "", [stage])
        tid = doc["task"]["id"]
        self.store.dispatch(tid, "inspect")
        self.store.started(tid, "inspect")
        self.assertTrue(self.policy.decide(self.req(tid, stage))["allowed"])

    def test_per_task_budget_rejects_split_writes(self):
        self.assertLess(MAX_TASK_WRITES, 32)
        stages = [self.stage(key="write" + str(i))
                  for i in range(MAX_TASK_WRITES + 1)]
        doc = self.store.create("many writes", "", stages)
        tid = doc["task"]["id"]
        self.store.approve(tid, "write0")
        self.store.dispatch(tid, "write0")
        self.store.started(tid, "write0")
        self.assertFalse(self.policy.decide(self.req(tid, stages[0]))["allowed"])

    def test_recent_write_limit_spans_tasks(self):
        # Build exactly the global budget of already-dispatched stage attempts.
        for i in range(MAX_RECENT_WRITES):
            stage = self.stage(key="write")
            doc = self.store.create("fixture " + str(i), "", [stage])
            tid = doc["task"]["id"]
            self.store.approve(tid, "write")
            self.store.dispatch(tid, "write")
            self.store.started(tid, "write")
            self.store.finished(tid, "write", result={"fixture": i})
        stage = self.stage()
        doc = self.store.create("budget overflow", "", [stage])
        tid = doc["task"]["id"]
        self.store.approve(tid, "write")
        self.store.dispatch(tid, "write")
        self.store.started(tid, "write")
        self.assertFalse(self.policy.decide(self.req(tid, stage))["allowed"])

    def test_private_unix_ipc_and_unavailable_fail_closed(self):
        sockdir = self.root / "runtime"
        sockdir.mkdir(mode=0o700)
        sock = sockdir / "broker.sock"
        server = serve(self.policy, sock)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        client = BrokerClient(sock)
        try:
            self.assertTrue(client.authorize_read("workspace.tree", {"path": "."})["allowed"])
            with self.assertRaises(BrokerDenied):
                client.authorize_read("file.replace", self.stage()["arguments"])
        finally:
            server.shutdown()
            thread.join(timeout=4)
            server.server_close()
        with self.assertRaises(BrokerDenied):
            client.authorize_read("workspace.tree", {"path": "."})

if __name__ == "__main__":
    unittest.main()
