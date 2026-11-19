"""Regression tests for staged handoff, audit data, and Git worktree isolation."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from aiws.store import Store
from aiws.gitops import create_task_worktree


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root)
        self.store.create_project("demo")

    def tearDown(self):
        self.temp.cleanup()

    def new(self, agent="dual"):
        return self.store.create_task("重构", "请审查代码并进行重构", "demo", agent, "reason")

    def test_dual_three_stage_gate_and_persist(self):
        task = self.new()
        self.assertEqual([s["agent"] for s in self.store.workflow(task["id"])],
                         ["claude", "codex", "claude"])
        with self.assertRaises(ValueError):
            self.store.finish_step(task["id"], "done", "cannot skip planning")
        first = self.store.task_brief(task["id"])
        self.assertIn("Assigned agent: `claude`", first.read_text("utf-8"))
        with self.assertRaises(ValueError):
            self.store.finish_step(task["id"], "done", "")
        out = self.store.finish_step(task["id"], "done", "design handoff")
        self.assertEqual(out["status"], "pending")
        second = self.store.task_brief(task["id"])
        self.assertIn("Assigned agent: `codex`", second.read_text("utf-8"))
        self.assertIn("design handoff", second.read_text("utf-8"))
        self.assertTrue((self.store.tasks_root / f"{task['id']}-step-1.md").exists())
        store2 = Store(self.root)
        self.assertEqual(store2.active_step(task["id"])["step_index"], 1)
        store2.finish_step(task["id"], "done", "implementation tests passed")
        store2.task_brief(task["id"])
        final = store2.finish_step(task["id"], "done", "review accepted")
        self.assertEqual(final["status"], "done")
        self.assertIsNone(store2.active_step(task["id"]))
        with self.assertRaises(ValueError):
            store2.task_brief(task["id"])

    def test_failed_step_requires_reprepare(self):
        task = self.new("claude")
        self.store.task_brief(task["id"])
        self.store.finish_step(task["id"], "failed", "test failed")
        self.assertEqual(self.store.get(task["id"])["status"], "failed")
        with self.assertRaises(ValueError):
            self.store.finish_step(task["id"], "done", "skip")
        self.store.task_brief(task["id"])
        self.assertEqual(self.store.finish_step(task["id"], "done", "fixed")["status"], "done")

    def test_running_step_cannot_be_manually_completed(self):
        task = self.new("codex")
        self.store.task_brief(task["id"])
        self.store.start_step(task["id"])
        with self.assertRaises(ValueError):
            self.store.finish_step(task["id"], "done", "unsafe race")
        self.assertEqual(self.store.finish_step(task["id"], "done", "worker completed", allow_running=True)["status"], "done")

    def test_old_task_migration_retains_completed(self):
        task = self.new("dual")
        with self.store._conn() as db:
            db.execute("DELETE FROM workflow_steps WHERE task_id=?", (task["id"],))
            db.execute("UPDATE tasks SET status='done',result='legacy result' WHERE id=?", (task["id"],))
        store2 = Store(self.root)
        self.assertEqual(store2.get(task["id"])["status"], "done")
        self.assertIsNone(store2.active_step(task["id"]))

    @unittest.skipUnless(shutil.which("git"), "Git not installed")
    def test_worktree_requires_clean_git_and_is_isolated(self):
        project = self.store.project_path("demo")
        def git(*args):
            subprocess.run([shutil.which("git"), "-C", str(project), *args], check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        git("init")
        git("-c", "user.name=AIWS Test", "-c", "user.email=test@example.invalid", "commit", "--allow-empty", "-m", "initial")
        task = self.new("codex")
        (project / "pending.txt").write_text("dirty", encoding="utf-8")
        with self.assertRaises(ValueError):
            create_task_worktree(task, self.store)
        (project / "pending.txt").unlink()
        path = create_task_worktree(task, self.store)
        self.assertEqual(path, self.store.task_workspace(task["id"]))
        self.assertNotEqual(path, project)
        self.assertEqual(path.parent, self.store.worktree_root)
        with self.assertRaises(ValueError):
            create_task_worktree(task, self.store)

if __name__ == "__main__":
    unittest.main()
