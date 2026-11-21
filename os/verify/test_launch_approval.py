"""Approval path for desktop launches: DAG stage -> user approval -> Broker -> Agent -> workbench launcher.

The launcher is the only component that can reach the display, so it re-verifies the stage itself. A fake `launch`
callable replaces real GUI programs; nothing here starts a process.
"""
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))
import aiws_apps
from aiws_agent_client import AgentClient, AgentError
from aiws_agent_service import AgentCore, serve
from aiws_launcher import LauncherClient, LauncherDenied, LauncherPolicy, start_in_thread
from aiws_permission_broker import BrokerClient, BrokerPolicy, serve as serve_broker
from aiws_tasks import GuestTaskStore, TaskError, WRITE_TOOLS

STAGE = {"key": "open", "label": "Open the terminal", "tool": "app.launch", "arguments": {"id": "terminal"}, "dependsOn": []}

class ToolClassTests(unittest.TestCase):
    def test_launch_is_a_write_class_tool_everywhere(self):
        from aiws_toolplane import APP_LAUNCH_TOOLS, READ_TOOLS, catalog
        from aiws_local_model import MODEL_WRITE_TOOLS
        self.assertEqual(APP_LAUNCH_TOOLS, {"app.launch"})
        self.assertTrue(APP_LAUNCH_TOOLS <= WRITE_TOOLS)                 # needs persisted approval; the Broker keys off this set
        self.assertFalse(APP_LAUNCH_TOOLS & READ_TOOLS)
        self.assertIn("app.launch", MODEL_WRITE_TOOLS)                    # proposable (dataset v3), but ALWAYS a pending stage needing approval
        self.assertIn("app.launch", [t["name"] for t in catalog()])

    def test_plan_validation_accepts_only_registered_gui_programs(self):
        GuestTaskStore.validate_plan([STAGE])
        for bad in ("git", "viewer", "nope", "../x", ""):
            with self.assertRaises(TaskError, msg=bad):
                GuestTaskStore.validate_plan([{**STAGE, "arguments": {"id": bad}}])
        with self.assertRaises(TaskError):
            GuestTaskStore.validate_plan([{**STAGE, "arguments": {"id": "terminal", "args": "-e sh"}}])   # no free-form arguments

    def test_tool_plane_refuses_to_run_it_directly(self):
        from aiws_toolplane import invoke
        with tempfile.TemporaryDirectory() as ws, patch.dict(os.environ, {"AIWS_WORKSPACE": ws}), \
                patch("aiws_toolplane.protect_guest_workspace", return_value=True):
            with self.assertRaises(PermissionError):
                invoke("app.launch", {"id": "terminal"})

@unittest.skipUnless(os.name == "posix" and hasattr(socket, "SO_PEERCRED"), "Linux guest peer credentials required")
class EndToEndTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.workspace = self.root / "projects"; self.workspace.mkdir()
        self.env = patch.dict(os.environ, {"AIWS_WORKSPACE": str(self.workspace)}); self.env.start()
        self.patches = [patch("aiws_toolplane.protect_guest_workspace", return_value=True), patch("aiws_guest_ops.protect_guest_workspace", return_value=True)]
        [p.start() for p in self.patches]
        self.sockdir = self.root / "runtime"; self.sockdir.mkdir(mode=0o700)
        self.launched = []
        self.core = AgentCore(self.workspace, self.root / "state", singleton=False, broker=BrokerClient(self.sockdir / "broker.sock"),
                              launcher=LauncherClient(self.sockdir / "launcher.sock"))
        db = self.root / "state" / "aiws" / "tasks.sqlite3"
        self.broker = serve_broker(BrokerPolicy(db, self.root / "state" / "aiws" / "broker.sqlite3"), self.sockdir / "broker.sock")
        threading.Thread(target=self.broker.serve_forever, daemon=True).start()
        self.policy = LauncherPolicy(db, self.workspace, launch=lambda ident, ws: self.launched.append(ident) or {"started": True})
        self.launcher = start_in_thread(self.policy, self.sockdir / "launcher.sock")
        self.server = serve(self.core, self.sockdir / "agent.sock")
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.client = AgentClient(self.sockdir / "agent.sock")

    def tearDown(self):
        for s in (self.server, self.broker, self.launcher):
            s.shutdown(); s.server_close()
        self.core.close(); [p.stop() for p in self.patches]; self.env.stop(); self.temp.cleanup()

    def stage(self, tid):
        return self.client.request("task.get", {"id": tid})["stages"][0]

    def wait(self, tid):
        for _ in range(200):
            st = self.stage(tid)
            if st["state"] not in ("queued", "running"):
                return st
            time.sleep(0.01)
        return st

    def test_launch_needs_explicit_approval_then_runs_exactly_once(self):
        tid = self.client.request("task.create", {"title": "Open", "goal": "", "stages": [STAGE]})["task"]["id"]
        self.assertEqual(self.stage(tid)["approval"], 0)                      # created un-approved
        with self.assertRaises(AgentError):
            self.client.request("task.dispatch", {"id": tid, "key": "open"})  # cannot run before approval
        self.assertEqual(self.launched, [])
        self.client.request("task.approve", {"id": tid, "key": "open"})
        self.client.request("task.dispatch", {"id": tid, "key": "open"})
        final = self.wait(tid)
        self.assertEqual(final["state"], "completed", final)
        self.assertEqual(self.launched, ["terminal"])
        self.assertTrue(self.client.request("audit.verify")["valid"])
        with self.assertRaises(AgentError):
            self.client.request("task.dispatch", {"id": tid, "key": "open"})  # completed stages cannot be re-run
        self.assertEqual(self.launched, ["terminal"])

    def test_launcher_refuses_everything_except_the_exact_running_approved_stage(self):
        tid = self.client.request("task.create", {"title": "Open", "goal": "", "stages": [STAGE]})["task"]["id"]
        client = LauncherClient(self.sockdir / "launcher.sock")
        with self.assertRaises(LauncherDenied):                               # pending + unapproved: a process that finds the socket gets nothing
            client.launch(tid, "open", "terminal")
        self.client.request("task.approve", {"id": tid, "key": "open"})
        with self.assertRaises(LauncherDenied):                               # approved but not running
            client.launch(tid, "open", "terminal")
        with self.assertRaises(LauncherDenied):
            client.launch("0" * 32, "open", "terminal")                       # unknown task
        self.assertEqual(self.launched, [])

    def test_launcher_ignores_a_request_whose_app_differs_from_the_stage(self):
        tid = self.client.request("task.create", {"title": "Open", "goal": "", "stages": [STAGE]})["task"]["id"]
        self.client.request("task.approve", {"id": tid, "key": "open"})
        store = self.core.tasks
        store.dispatch(tid, "open"); store.started(tid, "open")               # now persisted as running + approved
        client = LauncherClient(self.sockdir / "launcher.sock")
        with self.assertRaises(LauncherDenied):
            client.launch(tid, "open", "chromium")                            # approved "terminal", asked for "chromium"
        self.assertEqual(client.launch(tid, "open", "terminal"), {"started": True})
        with self.assertRaises(LauncherDenied):
            client.launch(tid, "open", "terminal")                            # the receipt is spent: no replay while still running
        self.assertEqual(self.launched, ["terminal"])

    def test_malformed_requests_and_wrong_shapes_are_refused(self):
        for bad in ({}, {"taskId": "x"}, {"taskId": "a" * 32, "stageKey": "k", "id": "terminal", "extra": 1},
                    {"taskId": 5, "stageKey": "k", "id": "terminal"}, {"taskId": "a" * 32, "stageKey": "k", "id": "git"}):
            self.assertFalse(self.policy.decide(bad)["allowed"], bad)

    def test_a_missing_launcher_is_a_failed_stage_not_a_silent_success(self):
        self.launcher.shutdown(); self.launcher.server_close(); (self.sockdir / "launcher.sock").unlink()
        self.launcher = start_in_thread(LauncherPolicy(self.root / "nowhere.sqlite3", self.workspace), self.sockdir / "other.sock")
        tid = self.client.request("task.create", {"title": "Open", "goal": "", "stages": [STAGE]})["task"]["id"]
        self.client.request("task.approve", {"id": tid, "key": "open"})
        self.client.request("task.dispatch", {"id": tid, "key": "open"})
        final = self.wait(tid)
        self.assertEqual(final["state"], "failed"); self.assertEqual(self.launched, [])

class LaunchFunctionTests(unittest.TestCase):
    def test_policy_launch_uses_the_registry_command_not_the_request(self):
        aiws_apps._last_launch.clear(); calls = []
        aiws_apps.launch("terminal", "/ws", which=lambda n: "/usr/bin/" + n, popen=lambda argv, **kw: calls.append(argv))
        self.assertEqual(calls, [["/usr/bin/xfce4-terminal"]])

if __name__ == "__main__":
    unittest.main()
