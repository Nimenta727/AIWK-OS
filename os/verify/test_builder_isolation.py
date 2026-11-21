"""O4: user-isolation wiring in the supervisor. Uses a FAKE sudo script and a recording runner (no real UID switch)."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
from aiws_events import EventStore
from aiws_mandate import MandateStore
from aiws_supervisor import (ISOLATION_DEFAULT, SIGNAL_NAMES, Supervisor, SupervisorError, UserIsolation, default_isolation_factory,
                             load_builder_config, validate_isolation)

FAKE = str(Path(__file__).resolve().parent / "fixtures" / "fake_cli.py")
GOOD = {"provider": "claude", "projectDir": "app", "allowedTools": ["Read", "Edit", "Bash(npm test)"], "permissionMode": "default",
        "maxTurns": 20, "tokenBudget": {"input": 100000, "output": 50000}, "wallClockMinutes": 5}
FAKE_SUDO = """#!/bin/sh
# FAKE sudo for tests: drops "-n -u USER --" and runs the rest as the current user.
while [ "$1" != "--" ]; do shift; done
shift
exec "$@"
"""

class Base(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.base = Path(self.t.name)
        self.ws = self.base / "ws"
        (self.ws / "app" / ".git").mkdir(parents=True)
        self.sudo = self.base / "sudo"
        self.sudo.write_text(FAKE_SUDO); self.sudo.chmod(0o755)
        self.marker = self.base / "firewall.ok"
        self.marker.write_text("")
        self.calls = []
        self.setfacl_rc = 0
        self.mandates = MandateStore(self.base / "m", self.ws)
        self.events = EventStore(self.base / "e")
        self.scenario = ["ok"]
        self.sup = Supervisor(self.mandates, self.events, self.ws, launcher=lambda m, p, c: ([sys.executable, FAKE] + self.scenario, {}),
                              config=lambda: {"enabled": True, "envAllow": [], "isolation": {"mode": "user"}},
                              isolation_factory=self.factory, approval_timeout=30)

    def runner(self, argv, **kwargs):
        self.calls.append(list(argv))
        if Path(argv[0]).name == "sudo" and "kill" in argv:
            name = argv[argv.index("kill") + 1].lstrip("-")
            active = self.sup.active
            if active is not None:
                try:
                    os.killpg(active.proc.pid, getattr(signal, "SIG" + name))      # stand-in for `kill -NAME -1` as the sandbox user
                except ProcessLookupError:
                    pass
            return subprocess.CompletedProcess(argv, 0, "", "")
        rc = self.setfacl_rc if "setfacl" in Path(argv[0]).name else 0
        return subprocess.CompletedProcess(argv, rc, "", "")

    def factory(self, config):
        return UserIsolation("aiws-builder", "http://127.0.0.1:3128", runner=self.runner, marker=self.marker,
                             which=lambda tool: "/usr/bin/" + tool, sudo=str(self.sudo), setfacl="/usr/bin/setfacl", main_user="mainuser")

    def tearDown(self):
        run = self.sup.active
        if run is not None:
            self.sup._terminate(run); self.sup.wait(5)
        self.mandates.close(); self.events.close(); self.t.cleanup()

    def grant(self, **over):
        return self.mandates.grant({**GOOD, **over})

    def go(self, scenario, wait=20, **over):
        self.scenario = scenario if isinstance(scenario, list) else [scenario]
        started = self.sup.start(self.grant(**over)["id"], "build")
        self.assertTrue(self.sup.wait(wait))
        return self.mandates.run_get(started["runId"])

    def sudo_kills(self):
        return [c[c.index("kill") + 1].lstrip("-") for c in self.calls if Path(c[0]).name == "sudo" and "kill" in c]

class UserIsolationUnitTests(Base):
    def iso(self):
        return self.factory({})

    def test_wrap_runs_as_the_sandbox_user_with_a_minimal_environment(self):
        argv = self.iso().wrap(["/usr/bin/claude", "-p", "fix; rm -rf /"])
        self.assertEqual(argv[:6], [str(self.sudo), "-n", "-u", "aiws-builder", "--", "env"])
        self.assertEqual(argv[6], "-i")                                   # nothing from the parent environment survives
        self.assertEqual(argv[-3:], ["/usr/bin/claude", "-p", "fix; rm -rf /"])      # the prompt is still ONE argument
        env = dict(a.split("=", 1) for a in argv[7:-3])
        self.assertEqual(env["HTTPS_PROXY"], "http://127.0.0.1:3128")
        self.assertEqual(env["HOME"], "/var/lib/aiws-builder/home")
        self.assertEqual(env["PATH"], "/usr/local/bin:/usr/bin:/bin")
        self.assertTrue(all(k.upper() in ("PATH", "HOME", "LANG", "TERM", "NO_PROXY", "HTTPS_PROXY", "HTTP_PROXY") for k in env))

    def test_prepare_grants_acls_in_a_safe_order_and_cleanup_revokes(self):
        iso = self.iso()
        project = (self.ws / "app").resolve()
        iso.prepare(project)
        facl = [c for c in self.calls if c[0].endswith("setfacl")]
        grant = next(c for c in facl if "-R" in c and str(project) in c and "d:u:aiws-builder:rwX" in c)
        self.assertIn("u:aiws-builder:rwX", grant)
        self.assertIn("u:mainuser:rwX", grant)                            # files the builder creates stay editable by the owner
        git = next(c for c in facl if c[-1] == str(project / ".git"))
        self.assertIn("u:aiws-builder:rX", git)                           # .git (hooks, config) is read-only for the builder
        self.assertNotIn("u:aiws-builder:rwX", git)
        traverse = [c for c in facl if "u:aiws-builder:--x" in c]
        self.assertTrue(all(len(c) == 4 and c[1] == "-m" for c in traverse))          # traverse only, never recursive
        self.assertLess(self.calls.index(traverse[0]), self.calls.index(grant))
        self.calls.clear()
        iso.cleanup(project)
        revoke = [c for c in self.calls if "-x" in c]
        self.assertTrue(any("u:aiws-builder" in c and str(project) in c and "-R" in c for c in revoke))
        self.assertEqual(iso.touched, [])

    def test_fails_closed_without_firewall_marker_or_tools(self):
        self.marker.unlink()
        with self.assertRaises(SupervisorError):
            self.iso().prepare(self.ws / "app")
        self.marker.write_text("")
        link = self.base / "marker-link"
        os.symlink(self.marker, link)
        bad = UserIsolation("aiws-builder", "http://127.0.0.1:3128", runner=self.runner, marker=link, which=lambda t: "/x", sudo=str(self.sudo), setfacl="/x/setfacl")
        with self.assertRaises(SupervisorError):
            bad.check()
        none = UserIsolation("aiws-builder", "http://127.0.0.1:3128", runner=self.runner, marker=self.marker, which=lambda t: None,
                             sudo="/nonexistent/sudo", setfacl="/nonexistent/setfacl")
        with self.assertRaises(SupervisorError):
            none.check()
        self.assertEqual([c for c in self.calls if c[0].endswith("setfacl")], [])      # nothing was changed

    def test_signal_commands(self):
        iso = self.iso()
        for sig, name in SIGNAL_NAMES.items():
            self.calls.clear()
            iso.signal(sig)
            self.assertEqual(self.calls[0][1:], ["-n", "-u", "aiws-builder", "--", "kill", "-" + name, "-1"])
        with self.assertRaises(SupervisorError):
            iso.signal(signal.SIGUSR1)

    def test_config_validation_and_factory(self):
        self.assertEqual(validate_isolation({}), ISOLATION_DEFAULT)
        self.assertEqual(validate_isolation({"mode": "user"})["mode"], "user")
        for bad in ({"mode": "root"}, {"user": "Root"}, {"user": "a b"}, {"user": "x" * 40}, {"proxy": "http://example.com:3128"},
                    {"proxy": "https://127.0.0.1:3128"}, {"proxy": "http://127.0.0.1:3128/x"}, {"proxy": "http://0.0.0.0:3128"},
                    {"extra": 1}, "user", None):
            with self.assertRaises(SupervisorError, msg=bad):
                validate_isolation(bad)
        self.assertIsNone(default_isolation_factory({"isolation": {"mode": "none"}}))
        self.assertIsNone(default_isolation_factory({}))
        self.assertIsInstance(default_isolation_factory({"isolation": {"mode": "user"}}), UserIsolation)
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "builder.json"
            p.write_text(json.dumps({"enabled": True, "isolation": {"mode": "user", "user": "aiws-builder"}}))
            self.assertEqual(load_builder_config(p)["isolation"]["mode"], "user")
            p.write_text(json.dumps({"isolation": {"mode": "sudo"}}))
            with self.assertRaises(SupervisorError):
                load_builder_config(p)

class IsolatedRunTests(Base):
    def test_run_completes_through_sudo_with_a_minimal_environment(self):
        outfile = self.base / "env.json"
        secrets = {"ANTHROPIC_API_KEY": "sk-1", "MY_TOKEN": "t", "AWS_SECRET_ACCESS_KEY": "a"}
        with patch.dict(os.environ, secrets):
            run = self.go(["env", str(outfile)])
        self.assertEqual(run["state"], "completed")
        seen = json.loads(outfile.read_text())
        for name in secrets:
            self.assertNotIn(name, seen["env"])
        self.assertIn("HTTPS_PROXY", seen["env"])
        self.assertEqual(seen["cwd"], str((self.ws / "app").resolve()))
        facl = [c for c in self.calls if c[0].endswith("setfacl")]
        self.assertTrue(any("-x" in c for c in facl))                      # cleanup ran after the run
        self.assertEqual(self.sup.status()["isolation"], {"mode": "user", "user": "aiws-builder"})

    def test_a_failing_acl_grant_prevents_the_run_and_is_cleaned_up(self):
        self.setfacl_rc = 1
        with self.assertRaises(SupervisorError):
            self.sup.start(self.grant()["id"], "x")
        self.assertEqual(self.mandates.runs(), [])                         # no run was recorded, nothing was spawned
        self.assertTrue(any("-x" in c for c in self.calls if c[0].endswith("setfacl")))
        self.assertIsNone(self.sup.active)

    def test_missing_firewall_marker_refuses_to_start(self):
        self.marker.unlink()
        with self.assertRaises(SupervisorError):
            self.sup.start(self.grant()["id"], "x")
        self.assertEqual(self.mandates.runs(), [])

    def test_approval_pause_and_resume_use_stop_and_cont_through_sudo(self):
        self.scenario = ["tool", "Bash|git push origin main"]
        m = self.grant()
        started = self.sup.start(m["id"], "x")
        for _ in range(200):
            st = self.sup.status()["active"]
            if st and st["pending"]:
                break
            time.sleep(0.05)
        self.assertEqual(st["pending"]["category"], "git-push")
        self.assertIn("STOP", self.sudo_kills())
        self.assertEqual(Path("/proc/%d/stat" % self.sup.active.proc.pid).read_text().split(")")[1].split()[0], "T")
        self.sup.decide(started["runId"], True)
        self.assertTrue(self.sup.wait(10))
        self.assertIn("CONT", self.sudo_kills())
        self.assertEqual(self.mandates.run_get(started["runId"])["state"], "completed")

    def test_budget_kill_and_user_stop_signal_through_sudo_and_revoke_acls(self):
        run = self.go("overbudget", tokenBudget={"input": 2500, "output": 50000})
        self.assertEqual((run["state"], run["reason"]), ("killed", "token-budget"))
        self.assertIn("TERM", self.sudo_kills())
        self.calls.clear()
        self.scenario = ["hang"]
        started = self.sup.start(self.grant()["id"], "x")
        self.sup.stop(started["runId"])
        self.assertTrue(self.sup.wait(10))
        self.assertEqual(self.mandates.run_get(started["runId"])["state"], "stopped")
        self.assertIn("TERM", self.sudo_kills())
        self.assertTrue(any("-x" in c for c in self.calls if c[0].endswith("setfacl")))

    def test_none_mode_still_does_not_use_sudo(self):
        sup = Supervisor(self.mandates, self.events, self.ws, launcher=lambda m, p, c: ([sys.executable, FAKE, "ok"], {}),
                         config=lambda: {"enabled": True, "envAllow": []})
        sup.start(self.grant()["id"], "x")
        self.assertTrue(sup.wait(15))
        self.assertEqual([c for c in self.calls if Path(c[0]).name == "sudo"], [])

if __name__ == "__main__":
    unittest.main()
