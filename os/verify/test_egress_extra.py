"""The optional second egress allowlist: off unless the owner creates the file, strict when present, and the base list stays minimal."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INC = ROOT / "debian/config/includes.chroot"
sys.path.insert(0, str(ROOT / "runtime"))
from aiws_egress_proxy import Policy, PolicyError

class Extra(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.d = Path(self.t.name); self.addCleanup(self.t.cleanup)
        self.base = self.d / "base.conf"; self.base.write_text("api.deepseek.com\n")
    def test_missing_extra_file_adds_nothing(self):
        p = Policy.load_with_extra(self.base, self.d / "nope.conf"); self.assertEqual(p.exact, {"api.deepseek.com"}); self.assertFalse(p.allows("pypi.org", 443))
        self.assertEqual(Policy.load_with_extra(self.base, None).exact, {"api.deepseek.com"})
    def test_present_extra_file_is_merged_and_still_https_only(self):
        extra = self.d / "extra.conf"; extra.write_text("pypi.org\nfiles.pythonhosted.org\n"); p = Policy.load_with_extra(self.base, extra)
        self.assertTrue(p.allows("pypi.org", 443)); self.assertTrue(p.allows("api.deepseek.com", 443)); self.assertFalse(p.allows("pypi.org", 80)); self.assertFalse(p.allows("evil.example", 443))
    def test_a_malformed_extra_file_stops_the_proxy_instead_of_half_applying(self):
        for body in ("10.0.0.1\n", "*.com\n", "not a host\n", ""):
            extra = self.d / "bad.conf"; extra.write_text(body)
            with self.assertRaises(PolicyError, msg=body): Policy.load_with_extra(self.base, extra)
    def test_a_symlinked_or_oversized_extra_file_is_refused(self):
        real = self.d / "real.conf"; real.write_text("pypi.org\n"); link = self.d / "link.conf"; link.symlink_to(real)
        with self.assertRaises(PolicyError): Policy.load_with_extra(self.base, link)
        big = self.d / "big.conf"; big.write_text("pypi.org\n" + "# x\n" * 10000)
        with self.assertRaises(PolicyError): Policy.load_with_extra(self.base, big)
    def test_the_shipped_files_are_consistent(self):
        reg = Policy.load(INC / "etc/aiws/egress-registries.conf"); self.assertTrue({"pypi.org", "registry.npmjs.org", "proxy.golang.org", "index.crates.io", "api.nuget.org"} <= reg.exact); self.assertEqual(reg.suffixes, set())
        base = Policy.load(INC / "etc/aiws/egress-allow.conf"); self.assertTrue(base.exact.isdisjoint(reg.exact), "registries must not be in the always-on list"); self.assertIn("api.deepseek.com", base.exact)
        self.assertFalse((INC / "etc/aiws/egress-extra.conf").exists(), "the extra list must be opt-in, not shipped active")
        self.assertIn("--allow-extra /etc/aiws/egress-extra.conf", (INC / "etc/systemd/system/aiws-egress-proxy.service").read_text())

if __name__ == "__main__":
    unittest.main()
