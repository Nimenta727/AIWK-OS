"""O3: mandate validation/store and the builder supervisor, driven by a SYNTHETIC fake CLI."""
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
import aiws_supervisor as sup
from aiws_mandate import MandateError, MandateStore, validate_mandate
from aiws_events import EventStore
from aiws_supervisor import Supervisor, SupervisorError, classify_action, claude_argv, codex_argv, default_launcher, load_builder_config, validate_prompt

FAKE = str(Path(__file__).resolve().parent / "fixtures" / "fake_cli.py")
GOOD = {"provider": "claude", "projectDir": "app", "allowedTools": ["Read", "Edit", "Bash(npm test)"], "permissionMode": "default",
        "maxTurns": 20, "tokenBudget": {"input": 100000, "output": 50000}, "wallClockMinutes": 5}

def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:
        return Path("/proc/%d/stat" % pid).read_text().split(")")[1].split()[0] != "Z"
    except OSError:
        return False

class Base(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.base = Path(self.t.name)
        self.ws = self.base / "ws"
        (self.ws / "app").mkdir(parents=True)
        self.skew = [0.0]
        self.clock = lambda: time.time() + self.skew[0]
        self.mandates = MandateStore(self.base / "m", self.ws, clock=self.clock)
        self.events = EventStore(self.base / "e")
        self.scenario = ["ok"]
        self.env_allow = []
        self.sup = Supervisor(self.mandates, self.events, self.ws, launcher=self.launch, clock=self.clock,
                              config=lambda: {"enabled": True, "envAllow": self.env_allow}, approval_timeout=30)

    def launch(self, mandate, prompt, cwd):
        return [sys.executable, FAKE] + self.scenario, {}

    def tearDown(self):
        run = self.sup.active
        if run is not None:
            self.sup._terminate(run)
            self.sup.wait(5)
        self.mandates.close(); self.events.close(); self.t.cleanup()

    def grant(self, **over):
        return self.mandates.grant({**GOOD, **over})

    def run_scenario(self, scenario, mandate=None, wait=20, **over):
        self.scenario = scenario if isinstance(scenario, list) else [scenario]
        m = mandate or self.grant(**over)
        started = self.sup.start(m["id"], "build the app")
        self.assertTrue(self.sup.wait(wait), "run did not finish")
        return m, self.mandates.run_get(started["runId"])

class MandateValidationTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.ws = Path(self.t.name) / "ws"
        (self.ws / "app").mkdir(parents=True)
        (self.ws / "app" / "sub").mkdir()
        (self.ws / "file.txt").write_text("x")
        os.symlink(self.ws / "app", self.ws / "linked")
    def tearDown(self):
        self.t.cleanup()
    def v(self, **over):
        data = {**GOOD, **over}
        for k in [k for k, v in over.items() if v is None]:
            data.pop(k)
        return validate_mandate(data, self.ws, 1700000000)

    def test_good_mandate_is_normalised(self):
        m = self.v()
        self.assertEqual((m["projectDir"], m["expires"]), ("app", 1700000000 + 24 * 3600))
        self.assertTrue({"network", "shell", "outside-project"} <= set(m["needApprovalFor"]))
        self.assertTrue(m["requireMetering"])
        self.assertEqual(self.v(projectDir="app/sub")["projectDir"], "app/sub")

    def test_rejections(self):
        bad = [dict(provider="gpt"), dict(provider=None), dict(projectDir="/etc"), dict(projectDir="../x"), dict(projectDir="app/../.."),
               dict(projectDir="."), dict(projectDir=""), dict(projectDir="nope"), dict(projectDir="file.txt"), dict(projectDir="linked"),
               dict(projectDir=".git"), dict(projectDir="app\\x"), dict(projectDir="handoff"),
               dict(allowedTools=[]), dict(allowedTools=["Bash"]), dict(allowedTools=["*"]), dict(allowedTools=["Bash(*)"]),
               dict(allowedTools=["Bash(rm -rf /)"]), dict(allowedTools=["Bash(curl http://x)"]), dict(allowedTools=["Bash(a; b)"]),
               dict(allowedTools=["Bash(a && b)"]), dict(allowedTools=["Bash(a | b)"]), dict(allowedTools=["Bash(sudo ls)"]),
               dict(allowedTools=["Bash($(x))"]), dict(allowedTools=["no spaces allowed"]), dict(allowedTools=["R"] * 17), dict(allowedTools="Read"),
               dict(permissionMode="bypassPermissions"), dict(permissionMode="dontAsk"),
               dict(tokenBudget={"input": 1}), dict(tokenBudget={"input": -1, "output": 1}), dict(tokenBudget={"input": True, "output": 1}),
               dict(tokenBudget={"input": 10 ** 12, "output": 1}), dict(tokenBudget=None),
               dict(maxTurns=0), dict(maxTurns=201), dict(maxTurns=None), dict(wallClockMinutes=0), dict(wallClockMinutes=481),
               dict(needApprovalFor=["delete"]), dict(needApprovalFor=["network", "shell"]), dict(needApprovalFor=["network", "shell", "outside-project", "bogus"]),
               dict(requireMetering="yes"), dict(expiresInMinutes=0), dict(expiresInMinutes=10 ** 6), dict(extra=1)]
        for over in bad:
            with self.assertRaises(MandateError, msg=over):
                self.v(**over)

    def test_required_approvals_cannot_be_switched_off_but_others_can(self):
        m = self.v(needApprovalFor=["network", "shell", "outside-project"])
        self.assertNotIn("git-push", m["needApprovalFor"])

class MandateStoreTests(Base):
    def test_grant_get_revoke_expire_usage(self):
        m = self.grant(expiresInMinutes=10)
        self.assertEqual((m["state"], m["used"]), ("active", {"input": 0, "output": 0}))
        self.assertEqual([x["id"] for x in self.mandates.active()], [m["id"]])
        self.mandates.add_usage(m["id"], 100, 40)
        self.mandates.add_usage(m["id"], 1, 1)
        self.assertEqual(self.mandates.remaining(m["id"]), {"input": 100000 - 101, "output": 50000 - 41})
        self.skew[0] = 11 * 60
        self.assertEqual(self.mandates.get(m["id"])["state"], "expired")
        self.assertEqual(self.mandates.active(), [])
        m2 = self.grant()
        self.assertEqual(self.mandates.revoke(m2["id"])["state"], "revoked")
        self.assertEqual(self.mandates.active(), [])
        with self.assertRaises(MandateError):
            self.mandates.get("nope")

    def test_tampering_with_a_granted_mandate_is_detected(self):
        m = self.grant()
        with self.mandates.lock:
            body = json.loads(self.mandates.db.execute("SELECT body FROM mandates WHERE id=?", (m["id"],)).fetchone()[0])
            body["tokenBudget"]["input"] = 10 ** 9
            self.mandates.db.execute("UPDATE mandates SET body=? WHERE id=?", (json.dumps(body, sort_keys=True, separators=(",", ":")), m["id"]))
        with self.assertRaises(MandateError):
            self.mandates.get(m["id"])

    def test_directory_safety_and_orphans(self):
        link = self.base / "lnk"
        os.symlink(self.base, link)
        with self.assertRaises(MandateError):
            MandateStore(link, self.ws)
        with self.assertRaises(MandateError):
            MandateStore("relative", self.ws)
        m = self.grant()
        rid = self.mandates.run_create(m["id"], "s")
        self.assertEqual(self.mandates.run_get(rid)["state"], "running")
        Supervisor(self.mandates, self.events, self.ws, launcher=self.launch)       # a restart
        self.assertEqual(self.mandates.run_get(rid)["state"], "interrupted")

class StartGuardTests(Base):
    def test_disabled_revoked_expired_exhausted_and_bad_prompts_never_start(self):
        m = self.grant()
        off = Supervisor(self.mandates, self.events, self.ws, launcher=self.launch, config=lambda: {"enabled": False, "envAllow": []})
        with self.assertRaises(PermissionError):
            off.start(m["id"], "x")
        for bad in ("", "   ", "x" * 4001, "-rf", "a\x00b", None, 5):
            with self.assertRaises(SupervisorError, msg=bad):
                self.sup.start(m["id"], bad)
        self.mandates.revoke(m["id"])
        with self.assertRaises(PermissionError):
            self.sup.start(m["id"], "x")
        m2 = self.grant(expiresInMinutes=1)
        self.skew[0] = 120
        with self.assertRaises(PermissionError):
            self.sup.start(m2["id"], "x")
        self.skew[0] = 0
        m3 = self.grant()
        self.mandates.add_usage(m3["id"], 100000, 0)
        with self.assertRaises(PermissionError):
            self.sup.start(m3["id"], "x")
        self.assertEqual(self.mandates.runs(), [])          # nothing was even recorded as started

    def test_one_run_at_a_time_and_project_must_still_exist(self):
        self.scenario = ["hang"]
        m = self.grant()
        started = self.sup.start(m["id"], "x")
        with self.assertRaises(SupervisorError):
            self.sup.start(m["id"], "y")
        self.sup.stop(started["runId"])
        self.assertTrue(self.sup.wait(10))
        (self.ws / "app").rename(self.ws / "gone")
        with self.assertRaises(SupervisorError):
            self.sup.start(m["id"], "z")

class RunTests(Base):
    def test_completed_run_records_everything(self):
        m, run = self.run_scenario("ok")
        self.assertEqual((run["state"], run["used_in"], run["used_out"]), ("completed", 250, 60))   # provider TOTAL wins
        self.assertEqual(self.mandates.get(m["id"])["used"], {"input": 250, "output": 60})
        sessions = {s["session"]: s for s in self.events.sessions()}
        build = next(s for n, s in sessions.items() if n.startswith("build-"))
        self.assertEqual((build["agent"], build["status"], build["tokens"]["in"]), ("claude", "ok", 250))
        self.assertTrue(any(n.startswith("sup-") for n in sessions))
        self.assertEqual(self.sup.status()["active"], None)

    def test_budget_is_enforced_from_reported_usage_and_is_cumulative(self):
        m, run = self.run_scenario("overbudget", tokenBudget={"input": 2500, "output": 50000})
        self.assertEqual((run["state"], run["reason"]), ("killed", "token-budget"))
        self.assertGreaterEqual(run["used_in"], 2500)
        self.assertLess(run["used_in"], 2500 + 3000)                # overshoot bounded by what was reported
        with self.assertRaises(PermissionError):
            self.sup.start(m["id"], "again")                         # budget used up: cannot start again

    def test_cumulative_budget_across_runs(self):
        m = self.grant(tokenBudget={"input": 400, "output": 50000})
        _, first = self.run_scenario("ok", mandate=m)
        self.assertEqual(first["state"], "completed")               # 250 < 400
        _, second = self.run_scenario("ok", mandate=m)
        self.assertEqual((second["state"], second["reason"]), ("killed", "token-budget"))     # 250 + 250 >= 400

    def test_no_metering_means_no_run_unless_the_user_allowed_it(self):
        _, run = self.run_scenario("unknown")
        self.assertEqual((run["state"], run["reason"]), ("killed", "metering-unavailable"))
        self.assertEqual((run["used_in"], run["used_out"]), (0, 0))              # nothing was invented
        _, relaxed = self.run_scenario("unknown", requireMetering=False)
        self.assertEqual(relaxed["state"], "completed")

    def test_max_turns(self):
        _, run = self.run_scenario("turns", maxTurns=3)
        self.assertEqual((run["state"], run["reason"]), ("killed", "max-turns"))

    def test_wall_clock(self):
        self.scenario = ["hang"]
        m = self.grant(wallClockMinutes=1)
        started = self.sup.start(m["id"], "x")
        time.sleep(0.4)
        self.skew[0] = 120                                          # two minutes pass
        self.assertTrue(self.sup.wait(10))
        self.assertEqual(self.mandates.run_get(started["runId"])["reason"], "wall-clock")

    def test_user_stop_kills_the_whole_process_group(self):
        pidfile = self.base / "child.pid"
        self.scenario = ["child", str(pidfile)]
        m = self.grant()
        started = self.sup.start(m["id"], "x")
        for _ in range(100):
            if pidfile.exists() and pidfile.read_text():
                break
            time.sleep(0.05)
        child = int(pidfile.read_text())
        self.assertTrue(alive(child))
        self.sup.stop(started["runId"])
        self.assertTrue(self.sup.wait(10))
        for _ in range(60):
            if not alive(child):
                break
            time.sleep(0.05)
        self.assertFalse(alive(child))
        self.assertEqual(self.mandates.run_get(started["runId"])["state"], "stopped")
        with self.assertRaises(SupervisorError):
            self.sup.stop(started["runId"])

    def test_nonzero_exit_is_failed_and_stderr_is_redacted(self):
        _, run = self.run_scenario("exit3")
        self.assertEqual(run["state"], "failed")
        self.assertIn("exit 3", run["reason"])
        self.assertNotIn("abc123xyz", run["reason"])

    def test_garbage_flood_and_huge_lines_are_survived(self):
        _, flood = self.run_scenario("flood")
        self.assertEqual(flood["state"], "completed")
        s = next(x for x in self.events.sessions() if x["session"] == flood["session"])
        self.assertLess(s["events"], 400)                            # coalesced, not 20000
        _, big = self.run_scenario("bigline")
        self.assertEqual(big["state"], "completed")

class ApprovalTests(Base):
    def wait_pending(self):
        for _ in range(200):
            st = self.sup.status()["active"]
            if st and st["pending"]:
                return st
            time.sleep(0.05)
        self.fail("no approval was requested")

    def proc_state(self, pid):
        return Path("/proc/%d/stat" % pid).read_text().split(")")[1].split()[0]

    def test_sensitive_tools_pause_until_the_user_decides(self):
        cases = {"Bash|git push origin main": "git-push", "Bash|npm install left-pad": "install-dependency", "Bash|rm -rf build": "delete",
                 "Bash|curl https://example.com/x": "network", "Bash|sudo ls": "shell", "Edit|/etc/passwd": "outside-project",
                 "Edit|../../secret": "outside-project", "WebFetch|https://example.com": "network"}
        for arg, category in cases.items():
            self.scenario = ["tool", arg]
            m = self.grant()
            started = self.sup.start(m["id"], "x")
            pending = self.wait_pending()
            self.assertEqual(pending["pending"]["category"], category, arg)
            self.assertEqual(self.proc_state(self.sup.active.proc.pid), "T")           # really stopped, not just flagged
            self.sup.decide(started["runId"], True)
            self.assertTrue(self.sup.wait(10), arg)
            self.assertEqual(self.mandates.run_get(started["runId"])["state"], "completed", arg)

    def test_denial_and_timeout_terminate_the_run(self):
        self.scenario = ["tool", "Bash|git push origin main"]
        m = self.grant()
        started = self.sup.start(m["id"], "x")
        self.wait_pending()
        self.sup.decide(started["runId"], False)
        self.assertTrue(self.sup.wait(10))
        run = self.mandates.run_get(started["runId"])
        self.assertEqual((run["state"], run["reason"]), ("killed", "approval-denied"))
        self.sup.approval_timeout = 0.3
        started = self.sup.start(m["id"], "x")
        self.assertTrue(self.sup.wait(10))
        self.assertEqual(self.mandates.run_get(started["runId"])["reason"], "approval-timeout")

    def test_approval_wait_does_not_consume_build_time(self):
        self.scenario = ["tool", "Bash|git push origin main"]
        m = self.grant(wallClockMinutes=1)
        started = self.sup.start(m["id"], "x")
        self.wait_pending()
        self.skew[0] = 300                                           # five minutes pass while waiting for the user
        self.sup.decide(started["runId"], True)
        self.assertTrue(self.sup.wait(10))
        self.assertEqual(self.mandates.run_get(started["runId"])["state"], "completed")

    def test_optional_categories_can_be_switched_off_but_outside_project_never(self):
        self.scenario = ["tool", "Bash|git push origin main"]
        m = self.grant(needApprovalFor=["network", "shell", "outside-project"])
        self.sup.start(m["id"], "x")
        self.assertTrue(self.sup.wait(10))
        self.assertIsNone(self.mandates.runs()[0]["pending"])
        self.assertEqual(self.mandates.runs()[0]["state"], "completed")      # git push was not gated by this mandate
        self.scenario = ["tool", "Edit|/etc/hosts"]
        started = self.sup.start(m["id"], "x")
        self.assertEqual(self.wait_pending()["pending"]["category"], "outside-project")
        self.sup.decide(started["runId"], False)
        self.assertTrue(self.sup.wait(10))

    def test_decide_without_pending_is_an_error(self):
        with self.assertRaises(SupervisorError):
            self.sup.decide("nothing", True)

class ProcessHygieneTests(Base):
    def test_environment_is_sanitised_cwd_is_the_project_and_stdin_is_closed(self):
        outfile = self.base / "env.json"
        secrets = {"ANTHROPIC_API_KEY": "sk-1", "MY_TOKEN": "t", "AWS_SECRET_ACCESS_KEY": "a", "SECRET_X": "s", "GITHUB_TOKEN": "g"}
        with patch.dict(os.environ, secrets):
            self.run_scenario(["env", str(outfile)])
        seen = json.loads(outfile.read_text())
        self.assertEqual(seen["cwd"], str((self.ws / "app").resolve()))
        self.assertTrue(seen["stdin_eof"])
        self.assertIn("PATH", seen["env"])
        for name in secrets:
            self.assertNotIn(name, seen["env"])
        self.env_allow = ["ANTHROPIC_API_KEY"]                       # explicit opt-in only
        with patch.dict(os.environ, secrets):
            self.run_scenario(["env", str(outfile)])
        seen = json.loads(outfile.read_text())
        self.assertIn("ANTHROPIC_API_KEY", seen["env"])
        self.assertNotIn("MY_TOKEN", seen["env"])

    def test_no_shell_and_no_dangerous_calls_in_source(self):
        src = (ROOT / "runtime/aiws_supervisor.py").read_text(encoding="utf-8")
        self.assertIn("shell=False", src)
        for bad in ("shell=True", "os.system", "os.popen", "import socket", "urllib"):
            self.assertNotIn(bad, src)

class LauncherTests(unittest.TestCase):
    M = {**GOOD, "allowedTools": ["Read", "Bash(npm test)"], "needApprovalFor": [], "expires": 1}
    def test_argv_shapes_and_prompt_stays_one_argument(self):
        prompt = "fix it; rm -rf / && echo $(whoami)"
        a = claude_argv("/usr/bin/claude", self.M, prompt, "/w/app")
        self.assertEqual(a[a.index("-p") + 1], prompt)                  # one element: nothing is interpreted by a shell
        self.assertEqual(a[a.index("--allowedTools") + 1], "Read,Bash(npm test)")
        self.assertEqual(a[a.index("--permission-mode") + 1], "default")
        c = codex_argv("/usr/bin/codex", {**self.M, "provider": "codex"}, prompt, "/w/app")
        self.assertEqual((c[-1], c[c.index("--cd") + 1], c[c.index("--sandbox") + 1]), (prompt, "/w/app", "workspace-write"))

    def test_bypass_flags_are_never_generated(self):
        for provider in ("claude", "codex"):
            for mode in ("default", "plan", "acceptEdits"):
                launch = default_launcher(lambda name: "/usr/bin/" + name)
                argv, _ = launch({**self.M, "provider": provider, "permissionMode": mode}, "do it", "/w/app")
                joined = " ".join(argv)
                for flag in sup.FORBIDDEN_FLAGS:
                    self.assertNotIn(flag, joined)

    def test_missing_cli_and_flag_injection(self):
        with self.assertRaises(SupervisorError):
            default_launcher(lambda name: None)(self.M, "x", "/w")
        for bad in ("--dangerously-skip-permissions", " -p evil"):
            with self.assertRaises(SupervisorError):
                validate_prompt(bad)
        self.assertEqual(validate_prompt("  fine  "), "fine")

    def test_classify_action_table(self):
        p = "/w/app"
        table = [("Edit", "src/a.js", None), ("Edit", "/w/app/src/a.js", None), ("Edit", "/w/app", None), ("Edit", "/w/application/x", "outside-project"),
                 ("Edit", "/etc/passwd", "outside-project"), ("Read", "~/.ssh/id_rsa", "outside-project"), ("Read", "a/../../b", "outside-project"),
                 ("Bash", "npm test", None), ("Bash", "git status", None), ("Bash", "git push", "git-push"), ("Bash", "pip install x", "install-dependency"),
                 ("Bash", "rm file", "delete"), ("Bash", "wget http://x", "network"), ("Bash", "bash -c 'x'", "shell"), ("command", "npm install", "install-dependency"),
                 ("WebSearch", "q", "network"), ("mcp_fetch", "", "network"), ("Glob", "**/*.js", None)]
        for tool, detail, expected in table:
            self.assertEqual(classify_action(tool, detail, p), expected, (tool, detail))

class BuilderConfigTests(unittest.TestCase):
    def test_default_disabled_and_strict(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "builder.json"
            self.assertEqual(load_builder_config(p), {"enabled": False, "envAllow": []})
            p.write_text('{"enabled": true, "envAllow": ["HTTPS_PROXY"]}')
            self.assertEqual(load_builder_config(p), {"enabled": True, "envAllow": ["HTTPS_PROXY"]})
            for bad in ('{"enabled": "yes"}', '{"x": 1}', '{"envAllow": ["lower"]}', '{"envAllow": ["A"] }'.replace('["A"]', '["A"]*9') if False else '{"envAllow": "A"}', "[1]", "{bad"):
                p.write_text(bad)
                with self.assertRaises(SupervisorError, msg=bad):
                    load_builder_config(p)
            p.unlink(); os.symlink("/etc/passwd", p)
            with self.assertRaises(SupervisorError):
                load_builder_config(p)

if __name__ == "__main__":
    unittest.main()
