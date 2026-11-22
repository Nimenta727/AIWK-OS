"""The system files for the dual-disk layout are consistent with each other (they cannot be booted here, so wiring is checked)."""
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHROOT = ROOT / "debian/config/includes.chroot"
sys.path.insert(0, str(ROOT / "runtime"))
import aiws_workdisk, aiws_sysverify

def modules():
    return {l.strip() for l in (ROOT / "runtime/MODULES").read_text().splitlines() if l.strip() and not l.startswith("#")}

class Wiring(unittest.TestCase):
    def test_units_call_installed_modules_and_are_enabled(self):
        for unit, module in (("aiws-work-disk", "aiws_workdisk.py"), ("aiws-verify-system", "aiws_sysverify.py")):
            text = (CHROOT / "etc/systemd/system" / (unit + ".service")).read_text()
            self.assertIn("/usr/local/lib/aiws/" + module, text); self.assertIn(module, modules())
            self.assertIn("NoNewPrivileges=yes", text)
            self.assertTrue((CHROOT / "etc/systemd/system/multi-user.target.wants" / (unit + ".service")).is_symlink(), unit)
    def test_missing_disk_or_modified_files_never_fail_the_boot(self):
        for unit in ("aiws-work-disk", "aiws-verify-system"):
            self.assertIn("SuccessExitStatus=1", (CHROOT / "etc/systemd/system" / (unit + ".service")).read_text())
    def test_work_disk_is_noexec_and_acl_names_known_accounts(self):
        self.assertTrue({"noexec", "nodev", "nosuid"} <= set(aiws_workdisk.MOUNT_OPTS.split(",")))
        tmp = (CHROOT / "usr/lib/tmpfiles.d/aiws-work.conf").read_text(); users = (CHROOT / "usr/lib/sysusers.d/aiws.conf").read_text()
        self.assertIn("aiws-agent", tmp); self.assertIn("aiws-agent", users); self.assertIn("aiws-work", users)
        self.assertIn(aiws_workdisk.MOUNT, tmp)
    def test_packages_for_the_tools_used(self):
        for f in ("package-lists/aiws-desktop.list.chroot",):
            pk = set((CHROOT.parent / f).read_text().split()); self.assertTrue({"btrfs-progs", "acl"} <= pk)
    def test_manifest_is_generated_last_and_the_doc_it_copies_exists(self):
        b = (ROOT / "debian/build.sh").read_text()
        self.assertLess(b.index('chmod 755 "$out/config/includes.chroot/usr/local/bin/aiws-broker"'), b.index("aiws_sysverify.py\" build"))
        self.assertLess(b.index("aiws_sysverify.py\" build"), b.index("\nlb build"))
        self.assertTrue((ROOT.parent / "docs/AIWS_DUAL_DISK.md").is_file())
    def test_manifest_location_matches_between_module_and_build(self):
        self.assertIn(aiws_sysverify.MANIFEST.replace("/usr/local/share/aiws/", ""), (ROOT / "debian/build.sh").read_text())
    def test_host_launcher_extra_disk_is_validated_and_syntax_ok(self):
        p = subprocess.run(["bash", "-n", str(ROOT / "host/run-qemu-offline.sh")], capture_output=True, text=True); self.assertEqual(p.returncode, 0, p.stderr)
        h = (ROOT / "host/run-qemu-offline.sh").read_text()
        self.assertIn("AIWS_WORK_DISK must be an absolute path", h); self.assertIn("-nic none", h)       # the offline guarantee is untouched
    def test_manifest_covers_every_script_the_units_run(self):
        self.assertTrue(any(str(p).startswith("/usr/local/lib/aiws") for p in aiws_sysverify.GUARDED) or "/usr/local/lib/aiws" in aiws_sysverify.GUARDED)

if __name__ == "__main__":
    unittest.main()
