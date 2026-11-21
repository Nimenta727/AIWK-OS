"""Stage-1 guest file tools: mkdir/copy/move/trash/restore/stat. Offline, workspace-only."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
sys.path.insert(0, str(RUNTIME))
import aiws_toolplane as plane
import aiws_tasks
import aiws_mcp
import aiws_local_model
from aiws_permission_broker import DIRECT_READ

W = {"file.mkdir", "file.copy", "file.move", "file.trash", "file.restore"}

class FileOpsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aiws-fileops-")
        self.root = Path(self.temp.name) / "project"
        self.root.mkdir()
        self.old = os.environ.get("AIWS_WORKSPACE")
        os.environ["AIWS_WORKSPACE"] = str(self.root)

    def tearDown(self):
        if self.old is None:
            os.environ.pop("AIWS_WORKSPACE", None)
        else:
            os.environ["AIWS_WORKSPACE"] = self.old
        self.temp.cleanup()

    def inv(self, name, **a):
        return plane.invoke(name, a)

    def make(self, rel, text="hello\n"):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return self.inv("file.stat", path=rel)["sha256"]

    def test_registration_and_privilege_split(self):
        names = {t["name"] for t in plane.catalog()}
        self.assertTrue(W | {"file.stat"} <= names)
        self.assertTrue(W <= aiws_tasks.WRITE_TOOLS)          # require durable approval
        self.assertNotIn("file.stat", aiws_tasks.WRITE_TOOLS)
        self.assertIn("file.stat", DIRECT_READ)
        self.assertFalse(W & DIRECT_READ)
        self.assertFalse(W & {t["name"] for t in aiws_mcp.MCP_CATALOG})
        self.assertFalse(W & aiws_local_model.READ_TOOLS)     # model cannot propose writes yet
        self.assertIn("file.stat", aiws_local_model.READ_TOOLS)

    def test_mkdir(self):
        self.inv("file.mkdir", path="docs")
        self.assertTrue((self.root / "docs").is_dir())
        with self.assertRaisesRegex(ValueError, "exists"):
            self.inv("file.mkdir", path="docs")
        with self.assertRaisesRegex(ValueError, "Parent"):
            self.inv("file.mkdir", path="a/b")

    def test_copy_never_overwrites_and_checks_hash(self):
        sha = self.make("a.txt")
        self.inv("file.copy", path="a.txt", to="b.txt", expectedSha256=sha)
        self.assertEqual((self.root / "b.txt").read_text(), "hello\n")
        self.assertTrue((self.root / "a.txt").exists())
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.inv("file.copy", path="a.txt", to="b.txt", expectedSha256=sha)
        with self.assertRaisesRegex(ValueError, "Conflict"):
            self.inv("file.copy", path="a.txt", to="c.txt", expectedSha256="0" * 64)
        self.assertEqual([p.name for p in self.root.iterdir() if p.name.startswith(".aiws-")], [])

    def test_move_and_rename_file_and_directory(self):
        sha = self.make("a.txt")
        self.inv("file.mkdir", path="docs")
        self.inv("file.move", path="a.txt", to="docs/b.txt", expectedSha256=sha)
        self.assertFalse((self.root / "a.txt").exists())
        self.assertEqual((self.root / "docs/b.txt").read_text(), "hello\n")
        d = self.inv("file.stat", path="docs")
        self.assertEqual(d["type"], "dir")
        self.inv("file.move", path="docs", to="papers", expectedSha256=d["sha256"])
        self.assertTrue((self.root / "papers/b.txt").is_file())
        with self.assertRaisesRegex(ValueError, "into itself"):
            sub = self.inv("file.stat", path="papers")["sha256"]
            self.inv("file.mkdir", path="papers/in")
            sub = self.inv("file.stat", path="papers")["sha256"]
            self.inv("file.move", path="papers", to="papers/in/x", expectedSha256=sub)

    def test_move_refuses_overwrite_conflict_and_stale_hash(self):
        sha = self.make("a.txt")
        self.make("b.txt", "other")
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.inv("file.move", path="a.txt", to="b.txt", expectedSha256=sha)
        (self.root / "a.txt").write_text("changed")
        with self.assertRaisesRegex(ValueError, "Conflict"):
            self.inv("file.move", path="a.txt", to="c.txt", expectedSha256=sha)
        self.assertEqual((self.root / "b.txt").read_text(), "other")

    def test_escape_symlink_and_protected_paths(self):
        sha = self.make("a.txt")
        for bad in ("../x", "/etc/x", ".git/x", ".ssh/x", "a\\b"):
            with self.assertRaises((ValueError, PermissionError)):
                self.inv("file.move", path="a.txt", to=bad, expectedSha256=sha)
        os.symlink("/etc/passwd", self.root / "link")
        with self.assertRaises(ValueError):
            self.inv("file.trash", path="link", expectedSha256="0" * 64)
        with self.assertRaises(ValueError):
            self.inv("file.move", path="a.txt", to="link/x", expectedSha256=sha)
        with self.assertRaisesRegex(ValueError, "root"):
            self.inv("file.trash", path=".", expectedSha256="0" * 64)

    def test_directory_with_symlink_is_refused(self):
        (self.root / "d").mkdir()
        os.symlink("/etc/passwd", self.root / "d/l")
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.inv("file.stat", path="d")

    def test_trash_restore_roundtrip_and_hidden(self):
        sha = self.make("keep/a.txt")
        r = self.inv("file.trash", path="keep/a.txt", expectedSha256=sha)
        self.assertFalse((self.root / "keep/a.txt").exists())
        self.assertNotIn(plane.TRASH, " ".join(self.inv("workspace.tree")["files"]))
        self.assertEqual(self.inv("code.search", query="hello")["matches"], [])
        with self.assertRaisesRegex(ValueError, "managed only"):
            self.inv("file.stat", path=plane.TRASH + "/" + r["trashId"] + "/payload")
        out = self.inv("file.restore", trashId=r["trashId"])
        self.assertTrue(out["restored"])
        self.assertEqual((self.root / "keep/a.txt").read_text(), "hello\n")
        self.assertEqual(list((self.root / plane.TRASH).iterdir()), [])

    def test_trash_directory_and_restore_conflict(self):
        self.make("d/x.txt")
        fp = self.inv("file.stat", path="d")["sha256"]
        r = self.inv("file.trash", path="d", expectedSha256=fp)
        self.inv("file.mkdir", path="d")  # original path taken meanwhile
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.inv("file.restore", trashId=r["trashId"])
        (self.root / "d").rmdir()
        self.inv("file.restore", trashId=r["trashId"])
        self.assertTrue((self.root / "d/x.txt").is_file())

    def test_restore_detects_tampering_and_bad_ids(self):
        sha = self.make("a.txt")
        r = self.inv("file.trash", path="a.txt", expectedSha256=sha)
        (self.root / plane.TRASH / r["trashId"] / "payload").write_text("evil")
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            self.inv("file.restore", trashId=r["trashId"])
        for bad in ("../x", "short", "G" * 32, ""):
            with self.assertRaises(ValueError):
                self.inv("file.restore", trashId=bad)

    def test_tree_lists_empty_dirs_and_hides_trash(self):
        self.inv("file.mkdir", path="empty")
        self.make("d/x.txt")
        sha = self.inv("file.stat", path="d/x.txt")["sha256"]
        self.inv("file.trash", path="d/x.txt", expectedSha256=sha)
        tree = self.inv("workspace.tree")
        self.assertIn("empty", tree["dirs"])
        self.assertIn("d", tree["dirs"])
        self.assertNotIn(plane.TRASH, tree["dirs"])

    def test_trash_list(self):
        self.assertEqual(self.inv("file.trashList")["items"], [])
        sha = self.make("a.txt")
        r = self.inv("file.trash", path="a.txt", expectedSha256=sha)
        items = self.inv("file.trashList")["items"]
        self.assertEqual([(i["trashId"], i["original"], i["type"]) for i in items],
                         [(r["trashId"], "a.txt", "file")])
        self.assertIn("file.trashList", DIRECT_READ)
        self.assertNotIn("file.trashList", aiws_tasks.WRITE_TOOLS)

    def test_no_permanent_delete_tool(self):
        names = {t["name"] for t in plane.catalog()}
        self.assertFalse({n for n in names if "delete" in n or "remove" in n or "unlink" in n})

    def test_tasks_require_approval_for_every_new_write(self):
        from aiws_tasks import GuestTaskStore
        with tempfile.TemporaryDirectory() as t:
            store = GuestTaskStore(Path(t) / "state")
            try:
                args = {"file.mkdir": {"path": "x"}, "file.trash": {"path": "x", "expectedSha256": "0"},
                        "file.restore": {"trashId": "0" * 32}}
                stages = [{"key": k.split(".")[1], "label": k, "tool": k, "arguments": v, "dependsOn": []}
                          for k, v in args.items()]
                doc = store.create("fileops", "", stages)
                tid = doc["task"]["id"]
                for st in stages:
                    with self.assertRaises(aiws_tasks.TaskError):
                        store.dispatch(tid, st["key"])   # unapproved write must not dispatch
            finally:
                store.close()

if __name__ == "__main__":
    unittest.main()
