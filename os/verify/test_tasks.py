"""Persistent DAG/approval/restart and audit integration; no host-side execution."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))
from aiws_tasks import GuestTaskStore, TaskError

def stage(key, tool="workspace.tree", deps=None, args=None):
    return {"key": key, "label": "Check " + key, "tool": tool,
            "arguments": args if args is not None else {"path": "."},
            "dependsOn": deps if deps is not None else []}

class TaskStoreTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.folder = Path(self.t.name) / "state"
        self.store = GuestTaskStore(self.folder)

    def tearDown(self):
        self.store.close()
        self.t.cleanup()

    def test_dag_rejects_cycle_and_host_tool(self):
        with self.assertRaises(TaskError):
            self.store.create("Bad", "", [stage("a", deps=["b"]), stage("b", deps=["a"])])
        with self.assertRaises(TaskError):
            self.store.create("Bad", "", [stage("a", tool="host.run")])
        self.assertEqual(self.store.list(), [])

    def test_dependencies_approval_and_audit_chain(self):
        doc = self.store.create("Guest files", "Read then edit guest file",
                                [stage("inspect"), stage("edit", tool="file.replace",
                                deps=["inspect"], args={"path": "x", "text": "new",
                                                       "expectedSha256": ""})])
        taskid = doc["task"]["id"]
        with self.assertRaises(TaskError):
            self.store.dispatch(taskid, "edit")
        action = self.store.dispatch(taskid, "inspect")
        self.assertEqual(action["tool"], "workspace.tree")
        with self.assertRaises(TaskError):
            self.store.dispatch(taskid, "inspect")
        self.store.started(taskid, "inspect")
        self.store.finished(taskid, "inspect", {"files": []})
        with self.assertRaises(TaskError):
            self.store.dispatch(taskid, "edit")
        self.store.approve(taskid, "edit")
        action = self.store.dispatch(taskid, "edit")
        self.store.started(taskid, "edit")
        output = self.store.finished(taskid, "edit", {"written": True})
        self.assertEqual([x["state"] for x in output["stages"]], ["completed", "completed"])
        self.assertTrue(all(x["previous_hash"] and len(x["entry_hash"]) == 64
                            for x in self.store.audit(taskid)))
        self.assertEqual(len(self.store.list()), 1)

    def test_service_and_kernel_plan_validation(self):
        doc=self.store.create("Guest service","",[
            stage("inspect",tool="service.inspect",args={"service":"aiws-workbench.service"}),
            stage("restart",tool="service.restart",deps=["inspect"],
                  args={"service":"aiws-local-model.service"})])
        taskid=doc["task"]["id"]
        self.assertEqual(doc["stages"][1]["approval"],0)
        with self.assertRaises(TaskError):
            self.store.dispatch(taskid,"restart")
        for tool,args in [
          ("service.inspect",{"service":"host.service"}),
          ("kernel.stage",{"path":"../host.fragment","expectedSha256":"0"*64}),
          ("kernel.abandon",{"candidateId":"bad"})]:
            with self.assertRaises((TaskError,ValueError)):
                self.store.create("Rejected","",[stage("s",tool=tool,args=args)])

    def test_restart_marks_queued_and_running_interrupted(self):
        doc = self.store.create("Recover", "", [stage("first")])
        taskid = doc["task"]["id"]
        self.store.dispatch(taskid, "first")
        self.store.close()
        self.store = GuestTaskStore(self.folder)
        self.assertEqual(self.store.get(taskid)["stages"][0]["state"], "interrupted")
        action = self.store.dispatch(taskid, "first")
        self.store.started(taskid, "first")
        self.store.finished(taskid, "first", error="tool unavailable")
        self.assertEqual(self.store.get(taskid)["stages"][0]["state"], "failed")

if __name__ == "__main__":
    unittest.main()
