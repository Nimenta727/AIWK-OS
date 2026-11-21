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
        self.core=AgentCore(self.workspace,self.root/"state",singleton=False)
        self.sockdir=self.root/"runtime"
        self.sockdir.mkdir(mode=0o700)
        self.socket=self.sockdir/"agent.sock"
        self.server=serve(self.core,self.socket)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.client=AgentClient(self.socket)

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=3)
        self.server.server_close()
        self.core.close()
        self.p2.stop();self.p1.stop();self.env.stop()
        self.temp.cleanup()

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

if __name__=="__main__":
    unittest.main()
