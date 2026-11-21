"""Windows WorkTask history cannot become executable Linux commands on import."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"runtime"))
from aiws_windows_compat import convert_windows_task,WindowsImportError
from aiws_tasks import GuestTaskStore,TaskError

A="a"*32
B="b"*32
TASK="d"*32
HASH="1"*64
def legacy(graph=True):
    return {
        "Id":TASK,"Title":"Source Windows project","GraphMode":graph,
        "Steps":[
            {"Id":A,"Title":"Windows Codex planning","Agent":"Codex",
             "Status":"Completed","Instructions":"SECRET_WINDOWS_PROMPT",
             "Result":"SECRET_WINDOWS_RESULT","RequiresApproval":True,
             "ApprovalGranted":True,"DependsOn":[]},
            {"Id":B,"Title":"Manual review","Agent":"Manual","Status":"Pending",
             "RequiresApproval":False,"ApprovalGranted":False,
             "DependsOn":[A] if graph else []}
        ],
        "Unified":{"SchemaVersion":1,"Goal":"Move review state",
                   "Plans":[{"Sha256":HASH}],
                   "Artifacts":[{"Kind":"plan","ContentHash":HASH}],
                   "AgentRuns":[{"Id":"c"*32,"StageId":A,"Agent":"Codex","Status":"Completed"}]},
        "ExecutionRecords":[{"Kind":"stage.finished","Metadata":"SECRET_WINDOWS_EVIDENCE"}]
    }

class WindowsCompatTests(unittest.TestCase):
    def test_convert_graph_and_retain_only_hashes_not_sensitive_text(self):
        value=convert_windows_task(legacy())
        self.assertEqual(value["taskId"],TASK)
        self.assertEqual(value["stages"][1]["dependsOn"],[A])
        self.assertEqual(value["metadata"]["planRevisionSha256"],[HASH])
        self.assertEqual(value["metadata"]["artifactRefs"][0]["sha256"],HASH)
        self.assertEqual(value["metadata"]["agentRuns"][0]["stageId"],A)
        dump=json.dumps(value)
        for secret in ("SECRET_WINDOWS_PROMPT","SECRET_WINDOWS_RESULT","SECRET_WINDOWS_EVIDENCE"):
            self.assertNotIn(secret,dump)

    def test_plan_agent_workitem_and_execution_ledger_are_safe_history(self):
        task=legacy()
        task["Unified"]["Plans"]=[{"Id":"e"*32,"Sha256":HASH,
            "RelativePath":"private/SECRET_PLAN.md","LinkedAt":"2026-11-21T04:00:00+00:00"}]
        task["Unified"]["WorkItems"]=[{"Id":A,"StageId":A,"Title":"Planning",
            "Status":"Completed","Agent":"Codex","DependsOn":[]}]
        task["Unified"]["AgentRuns"][0].update({
            "AdapterId":"SECRET_ADAPTER","Evidence":"local-intent",
            "StartedAt":"2026-11-21T04:01:00Z"})
        task["ExecutionRecords"]=[{"Id":"f"*32,"StageId":A,"RunId":"c"*32,
            "Kind":"stage.finished","Evidence":"observed","Source":"aiws.local",
            "At":"2026-11-21T04:02:00Z","Metadata":"SECRET_WINDOWS_EVIDENCE"}]
        with tempfile.TemporaryDirectory() as home:
            store=GuestTaskStore(Path(home)/"aiws")
            doc=store.import_windows(task)
            evidence=doc["windowsImport"]["evidence"]
            self.assertEqual(evidence["planRevisions"][0]["sha256"],HASH)
            self.assertEqual(evidence["planRevisions"][0]["id"],"e"*32)
            self.assertEqual(evidence["agentRuns"][0]["evidence"],"local-intent")
            self.assertEqual(evidence["workItems"][0]["linuxState"],"unmapped")
            self.assertEqual(evidence["executionRecords"][0]["kind"],"stage.finished")
            self.assertEqual(evidence["workflowStages"][0]["sourceStatus"],"Completed")
            self.assertTrue(all(s["state"]=="unmapped" for s in doc["stages"]))
            self.assertTrue(all(s["approval"]==0 for s in doc["stages"]))
            serialized=json.dumps(doc,ensure_ascii=False)
            for forbidden in ("SECRET_WINDOWS_EVIDENCE","SECRET_ADAPTER","SECRET_PLAN.md",
                              "SECRET_WINDOWS_PROMPT","SECRET_WINDOWS_RESULT"):
                self.assertNotIn(forbidden,serialized)
            with self.assertRaises(TaskError):
                store.dispatch(TASK,A)
            store.close()
            reopened=GuestTaskStore(Path(home)/"aiws")
            self.assertEqual(reopened.get(TASK)["windowsImport"]["evidence"],evidence)
            self.assertTrue(reopened.verify_audit()["valid"])
            reopened.close()

    def test_reject_malformed_windows_event_provenance(self):
        task=legacy()
        task["ExecutionRecords"]=[{"Kind":"stage.finished","Metadata":23}]
        with self.assertRaises(WindowsImportError):
            convert_windows_task(task)
        task=legacy()
        task["Unified"]["WorkItems"]=[{"StageId":A,"Status":"Escalated","Agent":"Codex"}]
        with self.assertRaises(WindowsImportError):
            convert_windows_task(task)

    def test_sequential_mode_preserves_windows_execution_order(self):
        value=convert_windows_task(legacy(graph=False))
        self.assertEqual(value["stages"][0]["dependsOn"],[])
        self.assertEqual(value["stages"][1]["dependsOn"],[A])

    def test_rejects_malformed_windows_dependency_and_id(self):
        bad=legacy()
        bad["Steps"][1]["DependsOn"]=[B]
        with self.assertRaises(WindowsImportError):
            convert_windows_task(bad)
        bad=legacy()
        bad["Steps"][0]["Id"]="../../host"
        with self.assertRaises(WindowsImportError):
            convert_windows_task(bad)

    def test_import_evidence_is_bound_to_audited_digest(self):
        with tempfile.TemporaryDirectory() as home:
            store=GuestTaskStore(Path(home)/"aiws")
            doc=store.import_windows(legacy())
            self.assertTrue(doc["windowsImport"]["evidence"]["planRevisionSha256"])
            receipt=[x for x in store.audit(TASK)
                     if x["action"]=="windows.history_imported"]
            self.assertEqual(len(receipt),1)
            details=json.loads(receipt[0]["details"])
            self.assertEqual(len(details["evidenceSha256"]),64)
            # A database row mutation cannot silently alter migration history.
            previous=store.db.execute(
                "SELECT evidence_json FROM windows_imports WHERE task_id=?",(TASK,)).fetchone()[0]
            store.db.execute("UPDATE windows_imports SET evidence_json=? WHERE task_id=?",
                             ('{"graphMode":true}',TASK))
            with self.assertRaises(TaskError):
                store.get(TASK)
            store.db.execute("UPDATE windows_imports SET evidence_json=? WHERE task_id=?",
                             (previous,TASK))
            self.assertTrue(store.verify_audit()["valid"])
            store.close()

    def test_import_appears_in_single_durable_guest_store_but_never_dispatches(self):
        with tempfile.TemporaryDirectory() as home:
            root=Path(home)/"aiws"
            store=GuestTaskStore(root)
            doc=store.import_windows(legacy())
            self.assertEqual(doc["task"]["id"],TASK)
            self.assertEqual([s["state"] for s in doc["stages"]],["unmapped","unmapped"])
            self.assertEqual([s["tool"] for s in doc["stages"]],["windows.unmapped","windows.unmapped"])
            self.assertEqual([s["stage_key"] for s in doc["stages"]],[A,B])
            with self.assertRaises(TaskError):
                store.dispatch(TASK,A)
            with self.assertRaises(TaskError):
                store.approve(TASK,A)
            self.assertTrue(store.verify_audit()["valid"])
            self.assertNotIn("SECRET_WINDOWS_PROMPT",json.dumps(store.audit(TASK)))
            with self.assertRaises(Exception):
                store.import_windows(legacy())  # no silent overwrite/reimport
            store.close()
            store=GuestTaskStore(root)
            persisted=store.get(TASK)
            self.assertEqual(persisted["stages"][0]["state"],"unmapped")
            self.assertTrue(store.verify_audit()["valid"])
            store.close()

if __name__=="__main__":
    unittest.main()
