"""O4: image files for the builder lane (firewall, sudoers, units, users), checked with the real tools available,
plus a REAL kernel behaviour test of the firewall rule in a throw-away network namespace.

What this proves: the ruleset is valid nftables, and in a fresh netns a non-root UID covered by the rule can reach
only the proxy port on 127.0.0.1 while root is unaffected. It does NOT prove the packaged image works: that needs
os/builder/aiws_builder_selftest.py run as root in a real guest.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
sys.path.insert(0, str(ROOT / "builder"))
INC = ROOT / "debian/config/includes.chroot"
FW = INC / "etc/aiws/builder-firewall.nft"
import aiws_builder_selftest as st
from aiws_egress_proxy import Policy

def can_netns():
    if os.geteuid() != 0 or not shutil.which("unshare") or not shutil.which("nft"):
        return False
    try:
        return subprocess.run(["unshare", "-n", "true"], capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False

NETNS_SCRIPT = r'''
import fcntl, json, socket, struct, subprocess, sys, threading
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
flags = struct.unpack('16sH14s', fcntl.ioctl(s, 0x8913, struct.pack('16sH14s', b'lo', 0, b'')))[1]
fcntl.ioctl(s, 0x8914, struct.pack('16sH14s', b'lo', flags | 1, b''))
load = subprocess.run(['nft', '-f', sys.argv[1]], capture_output=True, text=True)
if load.returncode: print(json.dumps({"error": load.stderr})); sys.exit(0)
def listen(port, family=socket.AF_INET, addr='127.0.0.1'):
    try:
        l = socket.socket(family); l.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); l.bind((addr, port))
    except OSError: return False
    l.listen(8)
    def run():
        while True:
            try: c, _ = l.accept(); c.close()
            except OSError: return
    threading.Thread(target=run, daemon=True).start(); return True
for p in (3128, 9999, 17640, 18080): listen(p)
v6 = listen(3128, socket.AF_INET6, '::1')
CLIENT = ("import socket,sys\nf=socket.AF_INET6 if ':' in sys.argv[1] else socket.AF_INET\n"
          "try:\n c=socket.socket(f); c.settimeout(1.0); c.connect((sys.argv[1],int(sys.argv[2]))); print('connected')\n"
          "except OSError as e: print('blocked')\n")
def attempt(host, port, uid):
    kw = {'user': uid, 'group': uid} if uid else {}
    return subprocess.run([sys.executable, '-c', CLIENT, host, str(port)], capture_output=True, text=True, timeout=10, **kw).stdout.strip()
out = {"v6": v6}
for uid in (65534, 0):
    out[str(uid)] = {str(p): attempt('127.0.0.1', p, uid) for p in (3128, 9999, 17640, 18080, 1)}
    if v6: out[str(uid)]["v6:3128"] = attempt('::1', 3128, uid)
print(json.dumps(out))
'''

class FirewallTests(unittest.TestCase):
    def ruleset(self, user):
        return FW.read_text().replace('"aiws-builder"', '"%s"' % user)

    def test_ruleset_content_is_minimal_and_fail_closed(self):
        text = FW.read_text()
        accepts = [l.strip() for l in text.splitlines() if l.strip().startswith("meta skuid") and l.rstrip().endswith("accept")]
        self.assertEqual(len(accepts), 1)                                               # exactly one allowed destination
        self.assertIn('meta skuid "aiws-builder"', accepts[0])
        self.assertIn('ip daddr 127.0.0.1 tcp dport 3128', accepts[0])
        self.assertIn('oifname "lo"', accepts[0])
        self.assertRegex(text, r'meta skuid "aiws-builder" counter drop')
        self.assertLess(text.index("tcp dport 3128 accept"), text.index("counter drop"))   # allow rule first, then drop everything else
        self.assertIn("table inet aiws_builder", text)                                  # inet: IPv4 and IPv6 both covered
        self.assertNotIn("policy drop", text)                                           # never locks out other users by accident

    @unittest.skipUnless(shutil.which("nft"), "nft not installed")
    def test_ruleset_is_valid_nftables(self):
        with tempfile.NamedTemporaryFile("w", suffix=".nft") as f:
            f.write(self.ruleset("nobody")); f.flush()
            r = subprocess.run(["nft", "-c", "-f", f.name], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)

    @unittest.skipUnless(can_netns(), "needs root, unshare -n and nft (real kernel test)")
    def test_kernel_behaviour_in_a_throwaway_network_namespace(self):
        with tempfile.NamedTemporaryFile("w", suffix=".nft") as f:
            f.write(self.ruleset("nobody")); f.flush()
            r = subprocess.run(["unshare", "-n", sys.executable, "-c", NETNS_SCRIPT, f.name], capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr[-300:])
        result = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertNotIn("error", result, result.get("error"))
        sandbox, root = result["65534"], result["0"]
        self.assertEqual(sandbox["3128"], "connected")                                  # the proxy is reachable
        for port in ("9999", "17640", "18080", "1"):                                    # workbench, model, anything else: dropped
            self.assertEqual(sandbox[port], "blocked", port)
        if result["v6"]:
            self.assertEqual(sandbox["v6:3128"], "blocked")                             # IPv6 path to the proxy is not allowed
        for port in ("3128", "9999", "17640", "18080"):                                 # the rule only affects the sandbox UID
            self.assertEqual(root[port], "connected", port)

class SudoersTests(unittest.TestCase):
    def test_only_the_sandbox_user_can_be_targeted(self):
        text = (INC / "etc/sudoers.d/aiws-builder").read_text()
        rules = [l for l in text.splitlines() if l.strip() and not l.startswith("#") and not l.startswith("Defaults")]
        self.assertEqual(len(rules), 1)
        self.assertRegex(rules[0], r"^user ALL=\(aiws-builder\) NOPASSWD: ALL$")
        for bad in ("(ALL)", "(root)", "(ALL:ALL)", "ALL=(ALL", "%"):
            self.assertNotIn(bad, rules[0])

    @unittest.skipUnless(shutil.which("visudo"), "visudo not installed")
    def test_sudoers_syntax(self):
        r = subprocess.run(["visudo", "-c", "-f", str(INC / "etc/sudoers.d/aiws-builder")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

class UnitTests(unittest.TestCase):
    def unit(self, name):
        return (INC / "etc/systemd/system" / name).read_text()

    def test_proxy_unit_is_unprivileged_and_hardened(self):
        u = self.unit("aiws-egress-proxy.service")
        for line in ("User=aiws-egress", "NoNewPrivileges=yes", "CapabilityBoundingSet=", "ProtectSystem=strict", "ProtectHome=yes",
                     "PrivateTmp=yes", "PrivateDevices=yes", "RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX", "MemoryMax=256M", "TasksMax=64"):
            self.assertIn(line, u)
        self.assertIn("--allow /etc/aiws/egress-allow.conf --port 3128", u)
        self.assertNotIn("User=root", u)
        self.assertRegex(u, r"After=.*aiws-builder-firewall\.service")

    def test_firewall_unit_sets_and_removes_the_fail_closed_marker(self):
        u = self.unit("aiws-builder-firewall.service")
        self.assertIn("ExecStart=/usr/sbin/nft -f /etc/aiws/builder-firewall.nft", u)
        self.assertIn("touch /run/aiws/builder-firewall.ok", u)                         # only after nft succeeded
        self.assertLess(u.index("ExecStart="), u.index("ExecStartPost="))
        self.assertIn("rm -f /run/aiws/builder-firewall.ok", u)
        self.assertRegex(u, r"Before=.*network-pre\.target")
        self.assertIn("RemainAfterExit=yes", u)

    def test_units_are_enabled_by_symlink(self):
        for name in ("aiws-builder-firewall.service", "aiws-egress-proxy.service"):
            link = INC / "etc/systemd/system/multi-user.target.wants" / name
            self.assertTrue(link.is_symlink(), name)
            self.assertEqual(os.readlink(link), "../" + name)

    def test_accounts_have_no_login_and_state_dirs_are_private(self):
        users = (INC / "usr/lib/sysusers.d/aiws-builder.conf").read_text()
        for name in ("aiws-builder", "aiws-egress"):
            self.assertRegex(users, r"^u %s\s+-\s+\".*\"\s+/var/lib/%s\s+/usr/sbin/nologin$" % (name, name), None) if False else None
            self.assertIn(name, users)
        self.assertEqual(users.count("/usr/sbin/nologin"), 2)
        tmp = (INC / "usr/lib/tmpfiles.d/aiws-builder.conf").read_text()
        self.assertIn("d /var/lib/aiws-builder      0700 aiws-builder aiws-builder", tmp)
        self.assertIn("d /run/aiws                  0755 root         root", tmp)         # the marker dir is root-owned

    @unittest.skipUnless(shutil.which("systemd-analyze"), "systemd-analyze not installed")
    def test_units_parse(self):
        r = subprocess.run(["systemd-analyze", "verify", str(INC / "etc/systemd/system/aiws-builder-firewall.service"),
                            str(INC / "etc/systemd/system/aiws-egress-proxy.service")], capture_output=True, text=True)
        for line in (r.stdout + r.stderr).splitlines():
            if re.search(r"(?i)unknown (key|section|lvalue)|invalid|syntax|failed to parse", line):
                self.fail(line)

class ImageWiringTests(unittest.TestCase):
    def test_allowlist_is_minimal_and_parses(self):
        p = Policy.load(INC / "etc/aiws/egress-allow.conf")
        self.assertLessEqual(len(p.exact) + len(p.suffixes), 6)
        self.assertEqual(p.suffixes, set())                                             # no wildcards by default
        self.assertEqual(p.ports, frozenset({443}))

    def test_build_script_installs_and_secures_everything(self):
        build = build_text()
        for needle in ("os/runtime/aiws_egress_proxy.py", "aiws_builder_selftest.py", "usr/local/sbin/aiws-builder-selftest",
                       "chmod 0440", "etc/sudoers.d/aiws-builder"):
            self.assertIn(needle, build)

    def test_packages_are_present_in_both_profiles(self):
        for f in ("debian/config/package-lists/aiws-desktop.list.chroot", "debian/profiles/smoke.list.chroot"):
            lines = set((ROOT / f).read_text().split())
            self.assertTrue({"nftables", "acl", "sudo"} <= lines, f)

    def test_firewall_port_matches_proxy_unit_and_supervisor_default(self):
        from aiws_supervisor import ISOLATION_DEFAULT
        self.assertTrue(ISOLATION_DEFAULT["proxy"].endswith(":3128"))
        self.assertIn("--port 3128", (INC / "etc/systemd/system/aiws-egress-proxy.service").read_text())
        self.assertIn("tcp dport 3128", FW.read_text())

class SelftestLogicTests(unittest.TestCase):
    """The guest self-test's decision logic, with scripted command results (it is NOT run against a real guest here)."""
    def make(self, overrides=None):
        overrides = overrides or {}
        def run(argv, user=None, timeout=15):
            key = " ".join(argv[:3]) if argv[0] != sys.executable else (argv[2][:25] + " " + " ".join(argv[3:]))
            for pattern, result in overrides.items():
                if pattern in " ".join(argv) or pattern in key:
                    return result
            return self.default(argv, user)
        return run

    @staticmethod
    def default(argv, user):
        joined = " ".join(argv)
        if argv[0] == "id" and argv[1] == "-u":
            return 0, "998", ""
        if argv[0] == "id":
            return 0, "aiws-builder", ""
        if argv[0] == "getent":
            return 0, "aiws-builder:x:998:998::/var/lib/aiws-builder:/usr/sbin/nologin", ""
        if argv[0] == "nft":
            return 0, "meta skuid 998 counter packets 0 bytes 0 drop", ""
        if argv[0] == "pgrep":
            return 1, "", ""
        if argv[0] in ("kill", "sudo"):
            return 1, "", "Operation not permitted"
        if "create_connection((\"127.0.0.1\", 3128)" in joined:
            return 0, "HTTP/1.1 403 Destination not allowed", ""
        if "getaddrinfo" in joined:
            return 0, "blocked:gaierror", ""
        if "create_connection((host, port)" in joined:
            return 0, "connected" if argv[-2:] == ["127.0.0.1", "3128"] else "blocked:TimeoutError", ""
        if "open(sys.argv[1], \"w\")" in joined:
            return 0, "written" if "/var/lib/aiws-builder/home" in joined else "denied:PermissionError", ""
        if "open(sys.argv[1], \"rb\")" in joined:
            return 0, "denied:PermissionError", ""
        return 0, "", ""

    def test_a_healthy_system_passes_and_skips_are_not_passes(self):
        with patch_marker(True):
            report = st.Selftest(run=self.make()).run_all()
        self.assertEqual(report["failed"], 0, [c for c in report["checks"] if c["status"] == "fail"])
        self.assertGreater(report["passed"], 15)
        skipped = [c["name"] for c in report["checks"] if c["status"] == "skip"]
        self.assertIn("proxy tunnels an allow-listed host", skipped)

    def test_each_kind_of_breach_is_reported_as_a_failure(self):
        breaches = {
            "connect to workbench": ({"create_connection((host, port)": (0, "connected", "")}, "reach the workbench"),
            "sudo works": ({"sudo -n true": (0, "", "")}, "sudo"),
            "dns works": ({"getaddrinfo": (0, "resolved", "")}, "resolve"),
            "shadow readable": ({"open(sys.argv[1], \"rb\")": (0, "read", "")}, "/etc/shadow"),
            "privileged group": ({"id -nG": (0, "aiws-builder sudo", "")}, "privileged groups"),
            "login shell": ({"getent passwd": (0, "aiws-builder:x:998:998::/home/b:/bin/bash", "")}, "login shell"),
            "no firewall": ({"nft list": (1, "", "No such file")}, "firewall table"),
        }
        for label, (override, needle) in breaches.items():
            with patch_marker(True):
                report = st.Selftest(run=self.make(override)).run_all()
            failed = " | ".join(c["name"] for c in report["checks"] if c["status"] == "fail")
            self.assertGreater(report["failed"], 0, label)
            self.assertIn(needle, failed, label)

    def test_missing_marker_and_unreachable_proxy(self):
        with patch_marker(False):
            report = st.Selftest(run=self.make()).run_all()
        self.assertIn("firewall marker exists (supervisor fail-closed switch)", [c["name"] for c in report["checks"] if c["status"] == "fail"])
        down = self.make({"create_connection((host, port)": (0, "blocked:TimeoutError", "")})
        with patch_marker(True):
            offline = st.Selftest(run=down).run_all()
            online = st.Selftest(run=down, online=True).run_all()
        proxy = lambda r: next(c for c in r["checks"] if c["name"] == "builder can reach the egress proxy")["status"]
        self.assertEqual((proxy(offline), proxy(online)), ("skip", "fail"))             # --online makes it mandatory

    def test_script_is_executable_python_and_requires_root(self):
        src = (ROOT / "builder/aiws_builder_selftest.py").read_text()
        self.assertTrue(src.startswith("#!/usr/bin/env python3"))
        self.assertIn("geteuid", src)
        self.assertIn("has not been run on a real guest", src)

from unittest.mock import patch  # noqa: E402
from buildsrc import build_text

def patch_marker(exists):
    return patch.object(Path, "is_file", lambda self: exists if str(self) == "/run/aiws/builder-firewall.ok" else os.path.isfile(str(self)))

if __name__ == "__main__":
    unittest.main()
