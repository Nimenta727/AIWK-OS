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
