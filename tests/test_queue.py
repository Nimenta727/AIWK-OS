"""Approval/queue regression suite; no external CLI, credentials or network."""
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from aiws.execution import CLIAdapters, QueueEngine
from aiws.policy import public_policy, require
from aiws.store import Store


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name))
        project = self.store.project_path(self.store.create_project("demo"))
        (project / ".git").mkdir()
        self.task = self.store.create_task("Read me", "Inspect project", "demo", "codex", "rules")
        self.task_id = self.task["id"]

    def tearDown(self):
        self.temp.cleanup()

    def prepared(self):
        self.store.task_brief(self.task_id)
        return self.store.request_readonly(self.task_id)

    def test_requires_prepared_stage_and_git_root(self):
        with self.assertRaises(ValueError):
            self.store.request_readonly(self.task_id)
        self.store.task_brief(self.task_id)
        (self.store.project_path("demo") / ".git").rmdir()
        with self.assertRaises(ValueError):
            self.store.request_readonly(self.task_id)

    def test_one_time_approval_and_atomic_claim(self):
        approval = self.prepared()
        with self.assertRaises(ValueError):
            self.store.request_readonly(self.task_id)
        with self.assertRaises(ValueError):
            self.store.decide(approval["id"], "invalid")
        decision = self.store.decide(approval["id"], "approve")
        with self.assertRaises(ValueError):
            self.store.decide(approval["id"], "approve")
        job = self.store.claim_next_job()
        self.assertEqual(job["id"], decision["job_id"])
        self.assertIsNone(self.store.claim_next_job())
        with self.assertRaises(ValueError):
            self.store.finish_step(self.task_id, "done", "manual override")
        result = self.store.complete_job(job["id"], True, "Only scanned files")
        self.assertEqual(result["status"], "done")
        self.assertEqual(self.store.jobs()[0]["status"], "succeeded")
        with self.assertRaises(ValueError):
            self.store.complete_job(job["id"], True, "replay")

    def test_deny_does_not_queue(self):
        approval = self.prepared()
        decision = self.store.decide(approval["id"], "deny")
        self.assertIsNone(decision["job_id"])
        self.assertFalse(self.store.jobs())
        self.assertIsNone(self.store.claim_next_job())

    def test_cancel_before_claim_and_reapprove(self):
        approval = self.prepared()
        job_id = self.store.decide(approval["id"], "approve")["job_id"]
        self.store.cancel_queued(job_id)
        self.assertIsNone(self.store.claim_next_job())
        with self.assertRaises(ValueError):
            self.store.cancel_queued(job_id)
        self.assertEqual(self.store.request_readonly(self.task_id)["status"], "pending")

    def test_restart_interrupts_running_without_replay(self):
        approval = self.prepared()
        job_id = self.store.decide(approval["id"], "approve")["job_id"]
        self.store.claim_next_job()
        reopened = Store(Path(self.temp.name))
        self.assertEqual(reopened.jobs()[0]["status"], "interrupted")
        self.assertEqual(reopened.get(self.task_id)["status"], "failed")
        self.assertIsNone(reopened.claim_next_job())
        reopened.task_brief(self.task_id)
        approval_2 = reopened.request_readonly(self.task_id)
        self.assertNotEqual(approval_2["id"], approval["id"])
        job_2 = reopened.decide(approval_2["id"], "approve")["job_id"]
        self.assertNotEqual(job_id, job_2)

    def test_queued_persists_for_enabled_worker(self):
        approval = self.prepared()
        self.store.decide(approval["id"], "approve")
        other = Store(Path(self.temp.name))
        self.assertEqual(other.jobs()[0]["status"], "queued")
        seen = []
        def fake_executor(task, project, brief):
            seen.append((task["id"], project, brief))
            return True, "completed by mock"
        engine = QueueEngine(other,executor=fake_executor,interval=0.02)
        try:
            engine.start()
            for _ in range(100):
                if other.jobs()[0]["status"] == "succeeded":
                    break
                time.sleep(0.02)
            self.assertEqual(other.jobs()[0]["status"], "succeeded")
            self.assertEqual(len(seen), 1)
            self.assertIn("Assigned agent: `codex`", seen[0][2])
        finally:
            engine.stop()

    def test_policy_denies_unimplemented_tools(self):
        self.assertFalse(public_policy()["system_admin"]["implemented"])
        with self.assertRaises(ValueError):
            require("shell",confirmed=True,approved=True)
        with self.assertRaises(ValueError):
            require("codex_readonly")
        with self.assertRaises(ValueError):
            require("git_worktree")
        require("git_worktree",confirmed=True)
        require("codex_readonly",approved=True)
        self.assertTrue(CLIAdapters.inventory()["claude"]["interactive"])
        self.assertFalse(CLIAdapters.inventory()["claude"]["background_readonly"])


if __name__ == "__main__":
    unittest.main()
