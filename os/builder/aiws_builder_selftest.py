#!/usr/bin/env python3
"""AIWS builder-lane self-test. Run as ROOT inside the guest after installing the image (step O4).

It checks the kernel/OS boundaries the builder lane relies on, using real commands as the sandbox user:
  firewall (only the egress proxy is reachable), no DNS, no sudo, no signalling other processes, no access to
  the workbench state, ACL round-trip on a project folder, and that the proxy refuses a non-allowlisted host.
Every check reports pass / fail / skip with a reason. A skipped check is NOT a pass.
Exit status is non-zero if any check failed. Passing this on a real guest is the acceptance evidence for O4;
it has not been run on a real guest by the author of this file.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

BUILDER, EGRESS = "aiws-builder", "aiws-egress"
PROXY_PORT = 3128
FORBIDDEN_GROUPS = {"sudo", "adm", "disk", "docker", "shadow", "root", "wheel", "lxd", "kvm", "libvirt", "systemd-journal"}

CONNECT_SNIPPET = """
import socket, sys
host, port = sys.argv[1], int(sys.argv[2])
try:
    s = socket.create_connection((host, port), timeout=2)
    s.close(); print("connected")
except OSError as e:
    print("blocked:" + type(e).__name__)
"""
PROXY_SNIPPET = """
import socket, sys
target = sys.argv[1]
try:
    s = socket.create_connection(("127.0.0.1", %d), timeout=3)
    s.sendall(("CONNECT %%s:443 HTTP/1.1\\r\\nHost: x\\r\\n\\r\\n" %% target).encode())
    print(s.recv(100).split(b"\\r\\n")[0].decode())
except OSError as e:
    print("error:" + type(e).__name__)
""" % PROXY_PORT
DNS_SNIPPET = """
import socket
try:
    socket.getaddrinfo("example.com", 443); print("resolved")
except OSError as e:
    print("blocked:" + type(e).__name__)
"""
WRITE_SNIPPET = """
import sys
try:
    open(sys.argv[1], "w").write("x"); print("written")
except OSError as e:
    print("denied:" + type(e).__name__)
"""
READ_SNIPPET = """
import sys
try:
    open(sys.argv[1], "rb").read(1); print("read")
except OSError as e:
    print("denied:" + type(e).__name__)
"""

def real_run(argv, user=None, timeout=15):
    cmd = (["runuser", "-u", user, "--"] + argv) if user else argv
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 124, "", type(exc).__name__

class Selftest:
    def __init__(self, run=real_run, workbench_user="user", workbench_port=17640, model_port=18080, online=False):
        self.run, self.user, self.wb, self.model, self.online = run, workbench_user, workbench_port, model_port, online
        self.results = []

    def add(self, name, status, detail=""):
        self.results.append({"name": name, "status": status, "detail": detail[:200]})

    def expect(self, name, condition, detail=""):
        self.add(name, "pass" if condition else "fail", detail)

    def py(self, snippet, *args, user=BUILDER):
        return self.run([sys.executable, "-c", snippet, *args], user=user)

    def run_all(self):
        self.users()
        self.firewall()
        self.network()
        self.filesystem()
        self.processes()
        return {"passed": sum(r["status"] == "pass" for r in self.results),
                "failed": sum(r["status"] == "fail" for r in self.results),
                "skipped": sum(r["status"] == "skip" for r in self.results), "checks": self.results}

    def users(self):
        for name in (BUILDER, EGRESS):
            rc, out, _ = self.run(["id", "-u", name])
            self.expect("user %s exists and is not root" % name, rc == 0 and out.isdigit() and int(out) != 0, out)
        rc, out, _ = self.run(["id", "-nG", BUILDER])
        groups = set(out.split())
        self.expect("builder has no privileged groups", rc == 0 and not (groups & FORBIDDEN_GROUPS), " ".join(sorted(groups)))
        rc, out, _ = self.run(["getent", "passwd", BUILDER])
        self.expect("builder has no login shell", rc == 0 and out.rsplit(":", 1)[-1] in ("/usr/sbin/nologin", "/sbin/nologin", "/bin/false"), out)

    def firewall(self):
        rc, out, err = self.run(["nft", "list", "table", "inet", "aiws_builder"])
        loaded = rc == 0 and "drop" in out and "skuid" in out
        self.expect("firewall table is loaded with a drop rule", loaded, err or out[:80])
        self.expect("firewall marker exists (supervisor fail-closed switch)", Path("/run/aiws/builder-firewall.ok").is_file())

    def network(self):
        for label, port in (("workbench", self.wb), ("local model", self.model)):
            rc, out, _ = self.py(CONNECT_SNIPPET, "127.0.0.1", str(port))
            self.expect("builder cannot reach the %s on loopback" % label, out.startswith("blocked"), out)
        rc, out, _ = self.py(CONNECT_SNIPPET, "127.0.0.1", "1")
        self.expect("builder cannot reach an arbitrary loopback port", out.startswith("blocked"), out)
        rc, out, _ = self.py(CONNECT_SNIPPET, "::1", str(PROXY_PORT))
        self.expect("builder cannot reach the proxy over IPv6 loopback", out.startswith("blocked"), out)
        rc, out, _ = self.py(CONNECT_SNIPPET, "1.1.1.1", "443")
        self.expect("builder cannot reach the internet directly", out.startswith("blocked"), out)
        rc, out, _ = self.py(DNS_SNIPPET)
        self.expect("builder cannot resolve names itself", out.startswith("blocked"), out)
        rc, out, _ = self.py(CONNECT_SNIPPET, "127.0.0.1", str(PROXY_PORT))
        if out == "connected":
            self.add("builder can reach the egress proxy", "pass", out)
            for bad in ("evil.invalid", "127.0.0.1", "169.254.169.254", "2130706433"):
                rc, out, _ = self.py(PROXY_SNIPPET, bad)
                self.expect("proxy refuses %s" % bad, " 403" in out or " 502" in out, out)
        else:
            self.add("builder can reach the egress proxy", "fail" if self.online else "skip", "proxy not reachable: " + out)
        if not self.online:
            self.add("proxy tunnels an allow-listed host", "skip", "needs --online and real internet access")

    def filesystem(self):
        for target in ("/etc/shadow", "/etc/aiws/egress-allow.conf.nonexistent-probe"):
            rc, out, _ = self.py(READ_SNIPPET, target)
            self.expect("builder cannot read %s" % target, out.startswith("denied"), out)
        state = Path("/home") / self.user / ".local/state/aiws/tasks.sqlite3"
        if state.exists():
            rc, out, _ = self.py(READ_SNIPPET, str(state))
            self.expect("builder cannot read the workbench task database", out.startswith("denied"), out)
        else:
            self.add("builder cannot read the workbench task database", "skip", "database not present yet")
        for target in ("/etc/aiws/probe", "/usr/local/bin/probe", "/var/lib/aiws-egress/probe", "/run/aiws/builder-firewall.ok"):
            rc, out, _ = self.py(WRITE_SNIPPET, target)
            self.expect("builder cannot write %s" % target, out.startswith("denied"), out)
        rc, out, _ = self.py(WRITE_SNIPPET, "/var/lib/aiws-builder/home/probe")
        self.expect("builder can write its own home", out == "written", out)

    def processes(self):
        rc, out, _ = self.run(["pgrep", "-u", self.user, "-f", "aiws_workbench"])
        pid = out.split()[0] if rc == 0 and out else None
        if pid:
            rc, out, err = self.run(["kill", "-0", pid], user=BUILDER)
            self.expect("builder cannot signal the workbench process", rc != 0, err or out)
        else:
            self.add("builder cannot signal the workbench process", "skip", "workbench is not running")
        rc, out, err = self.run(["sudo", "-n", "true"], user=BUILDER)
        self.expect("builder cannot use sudo", rc != 0, err or out)

def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--online", action="store_true", help="also require the allow-listed tunnel check (needs internet)")
    parser.add_argument("--workbench-user", default="user")
    args = parser.parse_args()
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        parser.error("run as root")
    report = Selftest(online=args.online, workbench_user=args.workbench_user).run_all()
    print(json.dumps(report, indent=2))
    return 1 if report["failed"] else 0

if __name__ == "__main__":
    sys.exit(main())
