"""Static contract checks only: they do not prove ISO boot or hypervisor isolation."""
from pathlib import Path
import re
import stat
import unittest
from buildsrc import build_text

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "os/debian/config"

class AiwsOsContract(unittest.TestCase):
    def test_image_builder_keeps_executable_git_mode(self):
        builder = ROOT / "os/debian/build.sh"
        self.assertTrue(builder.stat().st_mode & stat.S_IXUSR,
                        "Image builder must retain Git mode 100755 for CI execution")

    def test_shell_2_native_launcher_and_input_contract(self):
        full = (CONFIG / "package-lists/aiws-desktop.list.chroot").read_text()
        smoke = (ROOT / "os/debian/profiles/smoke.list.chroot").read_text()
        for package in ("xfce4-appfinder", "xfce4-notifyd", "fcitx5", "fcitx5-chinese-addons"):
            self.assertIn(package, full.split())
            self.assertIn(package, smoke.split())
        shell = (CONFIG / "includes.chroot/usr/local/bin/aiws-session").read_text()
        self.assertIn("XMODIFIERS=@im=fcitx", shell)
        xml = (CONFIG / "includes.chroot/usr/local/share/aiws/shell/openbox.xml").read_text()
        for shortcut in ("W-space", "W-Return", "W-e", "W-b", "W-i", "A-Tab"):
            self.assertIn(shortcut, xml)

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

    def test_firmware_iso_and_native_shell_contract(self):
        shell = (CONFIG / "includes.chroot/usr/local/bin/aiws-session").read_text()
        browser = (CONFIG / "includes.chroot/usr/local/bin/aiws-open-workbench").read_text()
        smoke = (CONFIG / "includes.chroot/usr/local/bin/aiws-boot-smoke").read_text()
        firmware = (ROOT / "os/kernel/ci/firmware-iso-boot.sh").read_text()
        workflow = (ROOT / ".github/workflows/aiws-os-image-boot.yml").read_text()
        self.assertIn("xfce4-panel --disable-wm-check", shell)
        self.assertIn("openbox --config-file", shell)
        self.assertIn("--app=http://127.0.0.1:17640/", browser)
        self.assertNotIn("--kiosk", browser)
        self.assertIn("xclip -selection clipboard", smoke)
        self.assertIn("windowactivate --sync", smoke)
        # Found by booting the full image: "-loops 1" lets a desktop component's TARGETS query consume the only loop,
        # so the clipboard owner must stay alive until the value is read back.
        commands = "\n".join(x for x in smoke.splitlines() if not x.strip().startswith("#"))
        self.assertNotIn("-loops 1", commands)
        # Without it Chromium asks gnome-keyring for a new keyring and a password dialog covers the workbench on boot.
        self.assertIn("--password-store=basic", browser)
        self.assertIn("El Torito boot img", firmware)
        self.assertIn("AIWS_FIRMWARE_ISO_PASS", firmware)
        executable = "\n".join(x for x in firmware.splitlines()
                               if not x.strip().startswith("#"))
        for forbidden in (" -kernel ", " -initrd ", "-virtfs", "-nic user"):
            self.assertNotIn(forbidden, executable)
        self.assertIn("firmware: [bios, uefi]", workflow)

    def test_independent_broker_is_packaged_and_required(self):
        build = build_text()
        agent = (CONFIG / "includes.chroot/etc/systemd/user/aiws-agent.service").read_text()
        broker = (CONFIG / "includes.chroot/etc/systemd/user/aiws-permission-broker.service").read_text()
        boot = (CONFIG / "includes.chroot/usr/local/bin/aiws-boot-smoke").read_text()
        mcp = (ROOT / "os/runtime/aiws_mcp.py").read_text()
        self.assertIn("aiws_permission_broker.py", build)
        self.assertIn("aiws-broker", build)
        self.assertIn("Requires=aiws-permission-broker.service", agent)
        self.assertIn("NoNewPrivileges=yes", broker)
        self.assertIn("RestrictAddressFamilies=AF_UNIX", broker)
        self.assertIn("brokerReady", boot)
        self.assertIn('AgentClient().request("tool.read"', mcp)


if __name__ == "__main__":
    unittest.main()
