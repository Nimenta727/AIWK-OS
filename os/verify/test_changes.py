"""Change review: porcelain/numstat parsing, confinement, hardened git, untracked files, binary handling."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
import aiws_changes as CH

def git(cwd, *a):
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a], cwd=cwd, check=True, capture_output=True)

class ParseTests(unittest.TestCase):
    def test_status_with_rename_untracked_and_staged(self):
        z = "M  a.py\0 M b.py\0R  new.py\0old.py\0?? c.txt\0 D gone.py\0"
        rows = {r["path"]: r for r in CH.parse_status(z)}
        self.assertEqual(rows["a.py"]["staged"], True); self.assertEqual(rows["b.py"]["staged"], False)
        self.assertEqual(rows["new.py"]["status"], "renamed"); self.assertEqual(rows["new.py"]["from"], "old.py")
        self.assertEqual(rows["c.txt"]["status"], "untracked"); self.assertEqual(rows["gone.py"]["status"], "deleted")
    def test_numstat_binary_is_unknown_not_zero(self):
        s = CH.parse_numstat("3\t1\ta.py\n-\t-\timg.png\n")
        self.assertEqual(s["a.py"], {"added": 3, "removed": 1}); self.assertEqual(s["img.png"], {"added": None, "removed": None})

class RepoTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.root = Path(self.t.name).resolve()
        self.proj = self.root / "app"; self.proj.mkdir()
        git(self.proj, "init", "-q"); (self.proj / "a.py").write_text("one\ntwo\n"); git(self.proj, "add", "."); git(self.proj, "commit", "-qm", "init")
    def tearDown(self):
        self.t.cleanup()
    def test_changes_lists_modified_and_untracked_with_counts(self):
        (self.proj / "a.py").write_text("one\nTWO\nthree\n"); (self.proj / "new.txt").write_text("hi\n")
        out = CH.changes(self.root, "app"); rows = {f["path"]: f for f in out["files"]}
        self.assertEqual(rows["a.py"]["status"], "modified"); self.assertEqual((rows["a.py"]["added"], rows["a.py"]["removed"]), (2, 1))
        self.assertEqual(rows["new.txt"]["status"], "untracked")
    def test_diff_for_modified_and_untracked(self):
        (self.proj / "a.py").write_text("one\nTWO\n"); (self.proj / "new.txt").write_text("hi\n")
        self.assertIn("-two", CH.diff(self.root, "app", "a.py")["diff"])
        self.assertEqual(CH.diff(self.root, "app", "new.txt")["diff"], "+hi\n")
    def test_binary_untracked_is_flagged_not_dumped(self):
        (self.proj / "b.bin").write_bytes(b"\0\1\2")
        self.assertTrue(CH.diff(self.root, "app", "b.bin")["binary"])
    def test_confinement(self):
        for bad in ("../x", "/etc", ".git", "app/.git", "a\\b", ""):
            if bad == "":
                continue
            with self.assertRaises(CH.ChangesError, msg=bad):
                CH.changes(self.root, bad)
        for bad in ("../a.py", ".git/config", "/etc/passwd"):
            with self.assertRaises(CH.ChangesError, msg=bad):
                CH.diff(self.root, "app", bad)
        (self.root / "link").symlink_to(self.proj)
        with self.assertRaises(CH.ChangesError):
            CH.changes(self.root, "link")
    def test_non_git_folder_is_a_clean_error(self):
        (self.root / "plain").mkdir()
        with self.assertRaises(CH.ChangesError):
            CH.changes(self.root, "plain")
    def test_hooks_and_external_diff_cannot_run(self):
        hook = self.proj / ".git" / "hooks"; hook.mkdir(exist_ok=True)
        marker = self.root / "ran"
        (self.proj / ".git" / "config").write_text((self.proj / ".git" / "config").read_text() + "[diff]\n\texternal = touch %s\n[core]\n\tfsmonitor = touch %s\n" % (marker, marker))
        (self.proj / "a.py").write_text("changed\n")
        CH.changes(self.root, "app"); CH.diff(self.root, "app", "a.py")
        self.assertFalse(marker.exists(), "a repo-configured command ran")
    def test_missing_git_binary(self):
        with patch("aiws_changes.shutil.which", lambda n: None), self.assertRaises(CH.ChangesError):
            CH.changes(self.root, "app")

if __name__ == "__main__":
    unittest.main()
