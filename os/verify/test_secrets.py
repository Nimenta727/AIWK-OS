"""API key storage: private file only, never readable back through status, never inside the workspace."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))
import aiws_secrets as S

KEY = "sk-abcdef0123456789abcdef"

class Store(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.p = Path(self.t.name) / "cfg" / "deepseek.key"
    def tearDown(self): self.t.cleanup()
    def test_save_creates_a_private_file_and_status_hides_the_key(self):
        st = S.save(KEY, self.p)
        self.assertEqual((self.p.stat().st_mode & 0o777, self.p.parent.stat().st_mode & 0o777), (0o600, 0o700))
        self.assertEqual(st, {"configured": True, "source": "file", "last4": KEY[-4:], "problem": None}); self.assertNotIn(KEY, repr(st))
        self.assertEqual(S.load(self.p, {}), KEY)
    def test_clear_removes_it_and_is_idempotent(self):
        S.save(KEY, self.p); self.assertFalse(S.clear(self.p)["configured"]); self.assertFalse(self.p.exists()); self.assertFalse(S.clear(self.p)["configured"])
    def test_invalid_keys_are_rejected(self):
        for bad in ("", "short", "has space 12345678", "sk-\nabc12345678", "x" * 300, None, 5):
            with self.assertRaises(S.SecretError, msg=bad): S.save(bad, self.p)
        self.assertFalse(self.p.exists())
    def test_unsafe_files_are_refused_not_ignored(self):
        S.save(KEY, self.p); os.chmod(self.p, 0o644)
        with self.assertRaises(S.SecretError): S.load(self.p, {})
        self.assertIn("others", S.status(self.p, {})["problem"]); self.assertFalse(S.status(self.p, {})["configured"])
        os.chmod(self.p, 0o600); self.p.write_text("x" * 600); os.chmod(self.p, 0o600)
        with self.assertRaises(S.SecretError): S.load(self.p, {})
    def test_symlink_is_refused(self):
        S.save(KEY, self.p); link = self.p.parent / "link.key"; link.symlink_to(self.p)
        with self.assertRaises(S.SecretError): S.load(link, {})
    def test_environment_is_a_fallback_and_file_wins(self):
        self.assertEqual(S.load(self.p, {"DEEPSEEK_API_KEY": KEY}), KEY); self.assertEqual(S.status(self.p, {"DEEPSEEK_API_KEY": KEY})["source"], "env")
        self.assertIsNone(S.load(self.p, {"DEEPSEEK_API_KEY": "bad key"})); self.assertIsNone(S.load(self.p, {}))
        S.save(KEY, self.p); self.assertEqual(S.load(self.p, {"DEEPSEEK_API_KEY": "other-key-12345678"}), KEY)
    def test_never_inside_the_workspace(self):
        ws = Path(self.t.name) / "ws"; ws.mkdir()
        with self.assertRaises(S.SecretError): S.save(KEY, ws / "projects" / "deepseek.key", forbidden_roots=[ws])
        self.assertFalse((ws / "projects").exists() and any((ws / "projects").iterdir()))
        S.save(KEY, self.p, forbidden_roots=[ws])                       # outside: fine
    def test_save_replaces_atomically_and_leaves_no_temp_file(self):
        S.save(KEY, self.p); S.save(KEY[:-1] + "Z", self.p)
        self.assertEqual(sorted(x.name for x in self.p.parent.iterdir()), ["deepseek.key"]); self.assertTrue(S.load(self.p, {}).endswith("Z"))

if __name__ == "__main__":
    unittest.main()
