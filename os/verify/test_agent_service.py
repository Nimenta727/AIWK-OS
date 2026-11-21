"""Standalone guest Agent socket contract; no real host/system operations."""
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"runtime"))
from aiws_agent_client import AgentClient, AgentError, AgentUnavailable
from aiws_agent_service import AgentCore, serve
from aiws_permission_broker import BrokerClient, BrokerPolicy, serve as serve_broker

@unittest.skipUnless(os.name=="posix" and hasattr(socket,"SO_PEERCRED"),
                     "Linux guest private peer credentials required")
class StandaloneAgentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.workspace=self.root/"projects"
        self.workspace.mkdir()
        (self.workspace/"source.txt").write_text("Guest only")
        self.env=patch.dict(os.environ,{"AIWS_WORKSPACE":str(self.workspace)})
        self.env.start()
        self.p1=patch("aiws_toolplane.protect_guest_workspace",return_value=True)
        self.p2=patch("aiws_guest_ops.protect_guest_workspace",return_value=True)
        self.p1.start();self.p2.start()
        self.sockdir=self.root/"runtime"
        self.sockdir.mkdir(mode=0o700)
        self.broker_socket=self.sockdir/"broker.sock"
        self.core=AgentCore(self.workspace,self.root/"state",singleton=False,
                            broker=BrokerClient(self.broker_socket))
        self.broker_server=serve_broker(BrokerPolicy(
            self.root/"state"/"aiws"/"tasks.sqlite3",
            self.root/"state"/"aiws"/"broker-decisions.sqlite3"),
            self.broker_socket)
        self.broker_thread=threading.Thread(
            target=self.broker_server.serve_forever,daemon=True)
        self.broker_thread.start()
        self.socket=self.sockdir/"agent.sock"
        self.server=serve(self.core,self.socket)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.client=AgentClient(self.socket)

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=3)
        self.server.server_close()
        self.broker_server.shutdown()
        self.broker_thread.join(timeout=3)
        self.broker_server.server_close()
        self.core.close()
        self.p2.stop();self.p1.stop();self.env.stop()
        self.temp.cleanup()

    def test_broker_denies_direct_execution_when_unavailable(self):
        self.assertTrue(self.client.request("health")["brokerReady"])
        saved=self.core.broker
        self.core.broker=BrokerClient(self.sockdir/"unavailable.sock")
        try:
            self.assertFalse(self.client.request("health")["brokerReady"])
            with self.assertRaises(AgentError):
                self.client.request("tool.read",{"tool":"workspace.tree",
                    "arguments":{"path":"."}})
        finally:
            self.core.broker=saved

    def test_agent_ipc_persistent_task_lifecycle(self):
        self.assertTrue(self.client.request("health")["ready"])
        staged={"key":"inspect","label":"Inspect guest","tool":"workspace.tree",
                "arguments":{"path":"."},"dependsOn":[]}
        doc=self.client.request("task.create",{"title":"Inspect","goal":"","stages":[staged]})
        tid=doc["task"]["id"]
        self.assertEqual(self.client.request("task.get",{"id":tid})["stages"][0]["state"],"pending")
        self.client.request("task.dispatch",{"id":tid,"key":"inspect"})
        final=None
        for _ in range(150):
            final=self.client.request("task.get",{"id":tid})["stages"][0]
            if final["state"] not in ("queued","running"):
                break
            time.sleep(.01)
        self.assertEqual(final["state"],"completed",final)
        self.assertTrue(self.client.request("audit.verify")["valid"])
        self.assertTrue(self.client.request("task.list"))

    def test_file_reads_are_guest_agent_ops_not_host_or_direct_write(self):
        result=self.client.request("tool.read",
            {"tool":"workspace.tree","arguments":{"path":"."}})
        self.assertIn("source.txt",result["files"])
        doc=self.client.request("tool.read",
            {"tool":"file.read","arguments":{"path":"source.txt"}})
        self.assertEqual(doc["text"],"Guest only")
        with self.assertRaises(AgentError):
            self.client.request("tool.read",{"tool":"file.replace",
                "arguments":{"path":"source.txt","text":"host","expectedSha256":""}})
        with self.assertRaises(AgentError):
            self.client.request("tool.read",{"tool":"runtime.test","arguments":{"language":"python"}})

    def test_model_proposal_pending_and_kernel_write_guard(self):
        proposal={"tool":"file.read","arguments":{"path":"source.txt"},
                  "reason":"Review guest file"}
        doc=self.client.request("task.model",
            {"instruction":"Read my project file","proposal":proposal})
        self.assertEqual(doc["stages"][0]["state"],"pending")
        self.assertEqual(doc["stages"][0]["tool"],"file.read")
        with self.assertRaises(AgentError):
            self.client.request("guest.read",{"tool":"service.restart",
                "arguments":{"service":"aiws-local-model.service"}})
        with self.assertRaises(AgentError):
            self.client.request("task.create",{"title":"Host","goal":"","stages":[{
                "key":"host","label":"Bad","tool":"host.exec",
                "arguments":{},"dependsOn":[]}]})

    def test_agent_builds_fingerprinted_plan_from_raw_model_output_only(self):
        import hashlib
        raw={"steps":[{"tool":"system.info","arguments":{},"reason":"check"},
                      {"tool":"file.move","arguments":{"path":"source.txt","to":"moved.txt"},
                       "reason":"rename"}],"reason":"rename the file"}
        doc=self.client.request("task.model",{"instruction":"rename source","proposal":raw})
        self.assertEqual([s["tool"] for s in doc["stages"]],["system.info","file.move"])
        self.assertEqual(doc["stages"][1]["arguments"]["expectedSha256"],
                         hashlib.sha256(b"Guest only").hexdigest())
        self.assertEqual(doc["stages"][1]["approval"],0)          # needs explicit approval
        self.assertEqual(doc["stages"][1]["dependsOn"],["step1"])
        self.assertTrue((self.workspace/"source.txt").exists())   # nothing executed
        # A model-supplied fingerprint, a non-canonical (already validated) dict, or a
        # file the Agent cannot see must all be refused.
        bad=[{"tool":"file.move","arguments":{"path":"source.txt","to":"x","expectedSha256":"0"*64},"reason":"r"},
             {"tool":"file.stat","arguments":{"path":"source.txt"},"reason":"r","requiresReview":True},
             {"tool":"file.trash","arguments":{"path":"missing.txt"},"reason":"r"}]
        for proposal in bad:
            with self.assertRaises(AgentError):
                self.client.request("task.model",{"instruction":"x","proposal":proposal})

    def test_new_local_read_tools_pass_agent_and_broker(self):
        (self.workspace/"downloads").mkdir()
        (self.workspace/"downloads"/"a.iso").write_bytes(b"1234")
        listing=self.client.request("tool.read",{"tool":"download.list","arguments":{}})
        self.assertEqual(listing["downloads"][0]["path"],"downloads/a.iso")
        self.assertIn("memory",self.client.request("tool.read",{"tool":"system.info","arguments":{}}))
        self.assertFalse(self.client.request("tool.read",{"tool":"network.status","arguments":{}})["activeProbe"])
        with self.assertRaises(AgentError):
            self.client.request("tool.read",{"tool":"download.start","arguments":{"url":"https://example.com"}})

if __name__=="__main__":
    unittest.main()
