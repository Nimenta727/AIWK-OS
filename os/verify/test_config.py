"""Static contract checks only: they do not prove ISO boot or hypervisor isolation."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "os/debian/config"

class AiwsOsContract(unittest.TestCase):
    def test_live_package_list_supplies_desktop_and_languages(self):
        packages = set((CONFIG / "package-lists/aiws-desktop.list.chroot").read_text().split())
        for package in ("xfce4", "lightdm", "firefox-esr", "geany", "python3",
                        "nodejs", "openjdk-21-jdk", "rustc", "golang-go", "clang", "git"):
            self.assertIn(package, packages)

    def test_offline_launcher_has_no_guest_host_bridges(self):
        launcher = (ROOT / "os/host/run-qemu-offline.sh").read_text()
        self.assertIn("-nic none", launcher)
        self.assertIn("Refusing to run QEMU as host root", launcher)
        self.assertIn("-sandbox on", launcher)
        for forbidden in ("-virtfs", "-fsdev", "-device vfio-", "-device usb-host",
                          "hostfwd=", "-qmp ", "-monitor stdio", "-nic user"):
            self.assertNotIn(forbidden, launcher)

    def test_admin_entry_requires_user_presence(self):
        script = (CONFIG / "includes.chroot/usr/local/bin/aiws-admin-session").read_text()
        for required in ("-t 0", "-t 1", "systemd-detect-virt --vm --quiet",
                         "read -r -p", "GUEST-ROOT", "exec sudo -i"):
            self.assertIn(required, script)
        self.assertNotIn("NOPASSWD", script)

    def test_guest_hardening_is_only_guest(self):
        path = CONFIG / "includes.chroot/etc/sysctl.d/90-aiws-guest.conf"
        content = path.read_text()
        self.assertIn("Guest root can alter", content)
        for key in ("kernel.kptr_restrict", "kernel.dmesg_restrict",
                    "kernel.yama.ptrace_scope", "fs.protected_hardlinks"):
            self.assertRegex(content, rf"(?m)^{re.escape(key)}\s*=")

    def test_kernel_fragment_advertises_uncompiled_status(self):
        fragment = (ROOT / "os/kernel/aiws-kernel.fragment").read_text()
        self.assertIn("not yet compiled", fragment)
        self.assertIn("CONFIG_SECURITY_LANDLOCK=y", fragment)

if __name__ == "__main__":
    unittest.main()
