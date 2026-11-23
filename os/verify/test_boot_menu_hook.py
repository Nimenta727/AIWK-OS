"""The live-build binary hook must make BOTH boot menus continue on their own.

Background (CI audit 2026-11-23): the firmware ISO boot job failed for BIOS and UEFI on every run for ~22 min each,
with no kernel output on the serial console. live-build's menus wait forever by default:
  * isolinux.cfg has "timeout 0" (syslinux: 0 = no timeout)
  * GRUB's config.cfg has no "set timeout" line at all (GRUB: unset = no timeout)
The earlier hook only rewrote an existing "set timeout=N", so the UEFI menu still waited forever.
The fixtures below are the first lines of the real trixie live-build 20250505 templates.
"""
import pathlib
import shutil
import subprocess
import tempfile
import unittest

HOOK = pathlib.Path(__file__).resolve().parents[1] / "debian/config/hooks/normal/9010-aiws-boot-menu.hook.binary"

ISOLINUX_CFG = "include menu.cfg\ndefault vesamenu.c32\nprompt 0\ntimeout 0\n"
GRUB_CONFIG_CFG = (
    "set default=0\n\n"
    "if [ x$feature_default_font_path = xy ] ; then\n    font=unicode\nelse\n    font=$prefix/unicode.pf2\nfi\n\n"
    "insmod gfxterm\ninsmod png\n\nsource /boot/grub/theme.cfg\n\nterminal_output gfxterm\n"
)
GRUB_CFG = "source /boot/grub/config.cfg\n\n# Live boot\nmenuentry \"Live system\" {\n  linux /live/vmlinuz\n}\n"


@unittest.skipUnless(shutil.which("sh") and shutil.which("sed"), "needs a POSIX shell and sed")
class BootMenuHook(unittest.TestCase):
    def tree(self, grub_config=GRUB_CONFIG_CFG):
        root = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        (root / "isolinux").mkdir()
        (root / "boot/grub").mkdir(parents=True)
        (root / "isolinux/isolinux.cfg").write_text(ISOLINUX_CFG)
        (root / "boot/grub/config.cfg").write_text(grub_config)
        (root / "boot/grub/grub.cfg").write_text(GRUB_CFG)
        return root

    def run_hook(self, root):
        subprocess.run(["sh", str(HOOK)], cwd=root, check=True, timeout=30)

    def test_bios_menu_gets_a_finite_timeout(self):
        root = self.tree()
        self.run_hook(root)
        lines = (root / "isolinux/isolinux.cfg").read_text().splitlines()
        self.assertIn("timeout 30", lines)
        self.assertNotIn("timeout 0", lines)

    def test_uefi_menu_gets_a_timeout_even_though_the_template_has_none(self):
        root = self.tree()
        self.run_hook(root)
        text = (root / "boot/grub/config.cfg").read_text()
        self.assertEqual([l for l in text.splitlines() if l.strip().startswith("set timeout=")], ["set timeout=3"])
        self.assertTrue(text.startswith(GRUB_CONFIG_CFG), "the original template must be kept, only appended to")

    def test_an_existing_grub_timeout_is_rewritten_not_duplicated(self):
        root = self.tree(GRUB_CONFIG_CFG + "set timeout=0\n")
        self.run_hook(root)
        text = (root / "boot/grub/config.cfg").read_text()
        self.assertEqual([l for l in text.splitlines() if "set timeout=" in l], ["set timeout=3"])

    def test_running_twice_changes_nothing_more(self):
        root = self.tree()
        self.run_hook(root)
        first = {p: p.read_text() for p in root.rglob("*.cfg")}
        self.run_hook(root)
        self.assertEqual(first, {p: p.read_text() for p in root.rglob("*.cfg")})

    def test_missing_files_are_skipped(self):
        root = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        self.run_hook(root)          # an empty binary tree must not fail the build


if __name__ == "__main__":
    unittest.main()
