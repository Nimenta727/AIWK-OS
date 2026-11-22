"""The REAL supervisor launching the REAL native runner against the SYNTHETIC fake DeepSeek server."""
import hashlib
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "runtime")); sys.path.insert(0, str(HERE / "fixtures"))
import aiws_plans as P
import aiws_supervisor as sup
from aiws_events import EventStore
from aiws_mandate import MandateError, MandateStore, validate_mandate
from aiws_supervisor import Supervisor, SupervisorError
from fake_deepseek import FakeDeepSeek, KEY, reply, tool_call

GOOD = {"provider": "deepseek", "projectDir": "app", "allowedTools": ["file.read", "file.trash", "workspace.tree", "plan.propose", "plan.update", "agent.spawn"],
        "model": "deepseek-flash", "thinking": True, "effort": "high", "maxTurns": 20, "tokenBudget": {"input": 10 ** 7, "output": 10 ** 6}, "wallClockMinutes": 5,
        "needApprovalFor": ["delete", "network", "shell", "outside-project"], "planApproval": True}

class Rig(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.base = Path(self.t.name).resolve(); self.ws = self.base / "ws"; (self.ws / "app").mkdir(parents=True)
        (self.ws / "app" / "a.txt").write_text("hello")
        self.mandates = MandateStore(self.base / "m", self.ws); self.events = EventStore(self.base / "e")
        self.plans = P.PlanStore(self.base / "plans.json"); self.results = P.ResultStore(self.base / "results.json")
        self.fake = None; self.key = KEY
        self.sup = Supervisor(self.mandates, self.events, self.ws, launcher=self.launch, config=lambda: {"enabled": True, "envAllow": []},
                              approval_timeout=30, plans=self.plans, results=self.results, key_loader=lambda: self.key)
    def launch(self, mandate, prompt, cwd):
        return [sys.executable, str(ROOT / "runtime" / "aiws_cloud_agent.py")], {"AIWS_CLOUD_TEST": "1", "AIWS_CLOUD_TEST_URL": self.fake.url}
    def tearDown(self):
        run = self.sup.active
        if run is not None: self.sup._terminate(run); self.sup.wait(5)
        if self.fake: self.fake.close()
        self.mandates.close(); self.events.close(); self.t.cleanup()
    def start(self, script, wait=True, prompt="tidy up", **over):
        self.fake = FakeDeepSeek(script)
        m = self.mandates.grant({**GOOD, **over}); r = self.sup.start(m["id"], prompt, "en")
        if wait: self.assertTrue(self.sup.wait(30), "run did not finish")
        return m, r
    def wait_pending(self, timeout=15):
        end = time.time() + timeout
        while time.time() < end:
            st = self.sup.status()["active"]
            if st and st["pending"]: return st["pending"]
            time.sleep(0.05)
        self.fail("no approval became pending")
    def run_row(self, r): return self.mandates.run_get(r["runId"])
    def kinds(self, r): return [(e["kind"], e.get("tool"), e.get("status")) for e in self.events.events(r["session"], limit=500)]

class HappyPath(Rig):
    def test_a_run_completes_stores_the_answer_counts_tokens_and_leaks_nothing(self):
        m, r = self.start([reply("", [tool_call("file__read", {"path": "a.txt"})]), reply("The file says hello.")])
        row = self.run_row(r); self.assertEqual((row["state"], row["reason"]), ("completed", "exit 0")); self.assertGreater(row["used_in"], 0); self.assertGreater(row["used_out"], 0)
        self.assertEqual(self.results.last()["text"], "The file says hello."); self.assertEqual(self.results.last()["runId"], r["runId"])
        self.assertGreater(self.mandates.get(m["id"])["used"]["input"], 0)
        evs = self.events.events(r["session"], limit=500); self.assertTrue(all(e["agent"] == "deepseek" for e in evs))
        self.assertIn(("tool", "file.read", "ok"), self.kinds(r)); self.assertIsNone(self.sup.status()["active"])
        # the key must not be anywhere we persist: databases, event bodies, plan/result stores, run rows
        blob = b"".join(p.read_bytes() for p in self.base.rglob("*") if p.is_file())
        self.assertNotIn(KEY.encode(), blob)
    def test_the_key_is_sent_over_stdin_not_argv_or_environment(self):
        seen = {}
        def launch(mandate, prompt, cwd):
            argv, env = [sys.executable, str(ROOT / "runtime" / "aiws_cloud_agent.py")], {"AIWS_CLOUD_TEST": "1", "AIWS_CLOUD_TEST_URL": self.fake.url}
            seen["argv"], seen["env"] = argv, env; return argv, env
        self.sup.launcher = launch; self.start([reply("done")])
        self.assertNotIn(KEY, " ".join(seen["argv"])); self.assertNotIn(KEY, json.dumps(seen["env"]))
        self.assertEqual(self.fake.requests[0]["auth"], "Bearer " + KEY)                              # but the service did receive it
    def test_the_api_receives_the_models_thinking_effort_and_the_language_instruction(self):
        self.start([reply("done")], model="deepseek-v4-pro", effort="max")
        body = self.fake.requests[0]["body"]; self.assertEqual((body["model"], body["reasoning_effort"]), ("deepseek-v4-pro", "max")); self.assertIn("English", body["messages"][0]["content"])
    def test_missing_key_refuses_to_start_and_creates_no_run(self):
        self.key = None; self.fake = FakeDeepSeek(); m = self.mandates.grant(GOOD)
        with self.assertRaises(SupervisorError) as cm: self.sup.start(m["id"], "x")
        self.assertIn("No DeepSeek API key", str(cm.exception)); self.assertEqual(self.mandates.runs(5), []); self.assertIsNone(self.sup.active)
    def test_service_failure_marks_the_run_failed_with_a_reason(self):
        _, r = self.start([{"status": 402}]); row = self.run_row(r); self.assertEqual(row["state"], "failed")
        self.assertTrue(any(k[0] == "error" for k in self.kinds(r)))

class Gates(Rig):
    def trash_call(self): return tool_call("file__trash", {"path": "a.txt", "expectedSha256": hashlib.sha256(b"hello").hexdigest()})
    def test_a_delete_blocks_until_approved_then_runs(self):
        m, r = self.start([reply("", [self.trash_call()]), reply("deleted it")], wait=False)
        pending = self.wait_pending(); self.assertEqual((pending["category"], pending["tool"], pending["sync"]), ("delete", "file.trash", True))
        self.assertTrue((self.ws / "app" / "a.txt").exists(), "nothing may run before the user answers")
        self.assertEqual(self.sup.status()["active"]["state"], "awaiting-approval"); self.sup.decide(r["runId"], True); self.assertTrue(self.sup.wait(30))
        self.assertFalse((self.ws / "app" / "a.txt").exists()); self.assertEqual(self.run_row(r)["state"], "completed")
    def test_a_refusal_means_it_never_runs_and_the_run_carries_on(self):
        m, r = self.start([reply("", [self.trash_call()]), reply("ok, left it")], wait=False)
        self.wait_pending(); self.sup.decide(r["runId"], False); self.assertTrue(self.sup.wait(30))
        self.assertTrue((self.ws / "app" / "a.txt").exists()); self.assertEqual(self.run_row(r)["state"], "completed"); self.assertEqual(self.results.last()["text"], "ok, left it")
        self.assertIn(("approval", None, "denied"), [k for e in self.events.events("sup-" + r["runId"][:12], limit=50) for k in [(e["kind"], e.get("tool"), e.get("status"))]])
    def test_no_answer_in_time_ends_the_run_and_nothing_runs(self):
        self.sup.approval_timeout = 0.5
        m, r = self.start([reply("", [self.trash_call()]), reply("x")], wait=False); self.assertTrue(self.sup.wait(30))
        self.assertTrue((self.ws / "app" / "a.txt").exists()); self.assertIn(self.run_row(r)["state"], ("killed", "failed")); self.assertEqual(self.run_row(r)["reason"][:16], "approval-timeout")
    def test_time_spent_waiting_for_the_user_does_not_count_as_build_time(self):
        m, r = self.start([reply("", [self.trash_call()]), reply("ok")], wait=False, wallClockMinutes=1)
        self.wait_pending(); run = self.sup.active; before = run.deadline; time.sleep(0.6); self.sup.decide(r["runId"], False); self.assertTrue(self.sup.wait(30))
        self.assertGreater(run.deadline, before + 0.4)

class PlanFlow(Rig):
    PLAN = {"title": "Tidy", "goal": "g", "steps": [{"title": "Look", "tool": "workspace.tree"}, {"title": "Trash it", "tool": "file.trash", "targets": ["a.txt"], "depends_on": [1]}]}
    def test_plan_appears_structured_awaits_approval_then_progress_updates_it(self):
        m, r = self.start([reply("", [tool_call("plan__propose", self.PLAN)]), reply("", [tool_call("plan__update", {"step": 1, "state": "completed"})]),
                           reply("", [tool_call("plan__update", {"step": 2, "state": "completed"})]), reply("all done")], wait=False)
        pending = self.wait_pending(); self.assertEqual(pending["category"], "plan")
        plan = next(p for p in self.plans.list() if p["kind"] == "native")
        self.assertEqual((plan["status"], plan["runId"]), ("awaiting-approval", r["runId"])); self.assertEqual([s["risk"] for s in plan["steps"]], ["low", "high"]); self.assertEqual(plan["steps"][1]["deps"], ["n1"])
        self.sup.decide(r["runId"], True); self.assertTrue(self.sup.wait(30))
        plan = next(p for p in self.plans.list() if p["kind"] == "native"); self.assertEqual(plan["status"], "done"); self.assertEqual([s["state"] for s in plan["steps"]], ["completed", "completed"])
    def test_a_rejected_plan_does_not_kill_the_run(self):
        m, r = self.start([reply("", [tool_call("plan__propose", self.PLAN)]), reply("What would you like instead?")], wait=False)
        self.wait_pending(); self.sup.decide(r["runId"], False); self.assertTrue(self.sup.wait(30))
        self.assertEqual(self.run_row(r)["state"], "completed"); self.assertEqual(next(p for p in self.plans.list() if p["kind"] == "native")["status"], "rejected")

class Limits(Rig):
    def test_the_supervisor_enforces_the_token_budget_even_if_the_runner_did_not(self):
        m, r = self.start([reply("", [tool_call("workspace__tree", {})], usage_out=3000)] * 10, tokenBudget={"input": 10 ** 7, "output": 5000}, maxTurns=100)
        row = self.run_row(r); self.assertIn(row["state"], ("killed", "failed", "completed")); self.assertLessEqual(len(self.fake.requests), 4); self.assertLess(row["used_out"], 12000)
    def test_the_user_can_stop_a_run_while_it_waits(self):
        m, r = self.start([reply("", [tool_call("file__trash", {"path": "a.txt", "expectedSha256": "0" * 64})]), reply("x")], wait=False)
        self.wait_pending(); self.sup.stop(r["runId"]); self.assertTrue(self.sup.wait(30)); self.assertEqual(self.run_row(r)["state"], "stopped"); self.assertTrue((self.ws / "app" / "a.txt").exists())

class SubAgentsThroughTheSupervisor(Rig):
    def test_tree_data_arrives_in_the_event_store(self):
        import aiws_agent_tree as T
        m, r = self.start([reply("", [tool_call("agent__spawn", {"task": "Look at a.txt", "label": "Looker"})]), reply("", [tool_call("file__read", {"path": "a.txt"})]), reply("child done"), reply("parent done")])
        tree = T.build(self.events.events(r["session"], limit=500)); by = {n["id"]: n for n in tree["nodes"]}
        self.assertEqual((by["sub-1"]["parent"], by["sub-1"]["label"], by["sub-1"]["state"]), ("root", "Looker", "done")); self.assertIn({"kind": "file", "ref": "a.txt"}, by["sub-1"]["ctx"])

class MandateForDeepSeek(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.ws = Path(self.t.name) / "ws"; (self.ws / "app").mkdir(parents=True)
    def tearDown(self): self.t.cleanup()
    def v(self, **kw): return validate_mandate({**GOOD, **kw}, self.ws)
    def test_valid_and_defaults(self):
        m = self.v(); self.assertEqual((m["provider"], m["model"], m["thinking"], m["effort"], m["planApproval"]), ("deepseek", "deepseek-flash", True, "high", True))
        d = {k: v for k, v in GOOD.items() if k not in ("model", "thinking", "effort", "planApproval")}; self.assertEqual(validate_mandate(d, self.ws)["model"], "deepseek-flash")
    def test_only_native_tool_names_no_patterns_no_shell(self):
        for bad in (["Bash(npm test)"], ["Bash"], ["file.read; rm"], ["service.restart"], ["app.launch"], ["nope"], [], ["file.read"] * 0):
            with self.assertRaises(MandateError, msg=bad): self.v(allowedTools=bad)
    def test_bad_model_effort_flags(self):
        for kw in ({"model": "gpt-4"}, {"effort": "ultra"}, {"thinking": "yes"}, {"planApproval": 1}):
            with self.assertRaises(MandateError, msg=kw): self.v(**kw)
    def test_native_fields_are_refused_for_other_providers(self):
        base = {"provider": "claude", "projectDir": "app", "allowedTools": ["Read"], "maxTurns": 5, "tokenBudget": {"input": 10, "output": 10}, "wallClockMinutes": 5}
        for extra in ({"model": "deepseek-flash"}, {"thinking": True}, {"planApproval": True}):
            with self.assertRaises(MandateError): validate_mandate({**base, **extra}, self.ws)
        self.assertNotIn("model", validate_mandate(base, self.ws))                                  # unchanged shape for existing providers
    def test_write_is_an_optional_approval_but_network_shell_outside_stay_mandatory(self):
        self.assertIn("write", self.v(needApprovalFor=["write", "network", "shell", "outside-project"])["needApprovalFor"])
        with self.assertRaises(MandateError): self.v(needApprovalFor=["write"])
    def test_runner_tool_list_matches_the_mandate_whitelist(self):
        import aiws_cloud_agent as A, aiws_mandate as M
        self.assertEqual(set(M.NATIVE_TOOLS), set(A.NATIVE_TOOLS))
        import aiws_toolplane
        known = {t["name"] for t in aiws_toolplane.catalog()}
        self.assertTrue(set(A.READ_TOOLS + A.WRITE_TOOLS) <= known, "the runner offers a tool the tool plane does not have")
        self.assertFalse(set(A.READ_TOOLS) & aiws_toolplane.FILE_WRITE_TOOLS); self.assertTrue(set(A.WRITE_TOOLS) <= aiws_toolplane.FILE_WRITE_TOOLS)


class BuildToolThroughTheSupervisor(Rig):
    """Running programs is opt-in: off by default, on only with isolation or the owner's explicit (dangerous) setting."""
    CALL = lambda self: tool_call("build__run", {"language": "python", "action": "run", "target": "h.py"})
    def setUp(self):
        super().setUp(); (self.ws / "app" / "h.py").write_text("print('built and ran')\n")
        self.cfg = {"enabled": True, "envAllow": []}; self.sup.config = lambda: self.cfg
    def offered(self): return [t["function"]["name"] for t in self.fake.requests[0]["body"]["tools"]]
    def test_not_offered_by_default_and_status_says_why(self):
        self.assertFalse(self.sup.status()["execAllowed"])
        self.start([reply("done")], allowedTools=GOOD["allowedTools"] + ["build.run"]); self.assertNotIn("build__run", self.offered())
    def test_offered_and_gated_when_the_owner_accepted_the_risk(self):
        self.cfg["execWithoutIsolation"] = True; self.assertTrue(self.sup.status()["execAllowed"])
        m, r = self.start([reply("", [self.CALL()]), reply("all good")], wait=False, allowedTools=GOOD["allowedTools"] + ["build.run"],
                          needApprovalFor=["build", "network", "shell", "outside-project"])
        pending = self.wait_pending(); self.assertIn("build__run", self.offered())              # the first request has been sent by now
        self.assertEqual((pending["category"], pending["tool"], pending["sync"]), ("build", "build.run", True)); self.assertIn("h.py", pending["detail"])
        self.sup.decide(r["runId"], True); self.assertTrue(self.sup.wait(60)); self.assertEqual(self.run_row(r)["state"], "completed")
        self.assertIn("built and ran", json.dumps(self.fake.requests[1]["body"]["messages"]))
    def test_refusing_the_build_means_the_program_never_ran(self):
        self.cfg["execWithoutIsolation"] = True; (self.ws / "app" / "h.py").write_text("open('ran','w').write('x')\n")
        m, r = self.start([reply("", [self.CALL()]), reply("ok")], wait=False, allowedTools=GOOD["allowedTools"] + ["build.run"], needApprovalFor=["build", "network", "shell", "outside-project"])
        self.wait_pending(); self.sup.decide(r["runId"], False); self.assertTrue(self.sup.wait(60)); self.assertFalse((self.ws / "app" / "ran").exists())
    def test_the_built_program_does_not_see_the_key(self):
        self.cfg["execWithoutIsolation"] = True; (self.ws / "app" / "h.py").write_text("import os; print(sorted(os.environ))\n")
        self.start([reply("", [self.CALL()]), reply("ok")], allowedTools=GOOD["allowedTools"] + ["build.run"], needApprovalFor=["network", "shell", "outside-project"])
        self.assertNotIn(KEY, json.dumps(self.fake.requests[1]["body"]["messages"])); self.assertNotIn("DEEPSEEK", json.dumps(self.fake.requests[1]["body"]["messages"]))
    def test_config_key_is_validated(self):
        import tempfile as tf
        d = Path(tf.mkdtemp()); self.addCleanup(__import__("shutil").rmtree, d, True)
        good = d / "ok.json"; good.write_text('{"enabled": true, "execWithoutIsolation": true}'); self.assertTrue(sup.load_builder_config(good)["execWithoutIsolation"])
        self.assertFalse(sup.load_builder_config(d / "missing.json")["execWithoutIsolation"])
        bad = d / "bad.json"; bad.write_text('{"execWithoutIsolation": "yes"}')
        with self.assertRaises(SupervisorError): sup.load_builder_config(bad)
    def test_mandate_accepts_the_tool_and_the_category_and_keeps_shell_mandatory(self):
        m = validate_mandate({**GOOD, "allowedTools": ["file.read", "build.run"], "needApprovalFor": ["build", "network", "shell", "outside-project"]}, self.ws)
        self.assertIn("build.run", m["allowedTools"]); self.assertIn("build", m["needApprovalFor"])
        with self.assertRaises(MandateError): validate_mandate({**GOOD, "needApprovalFor": ["build"]}, self.ws)

if __name__ == "__main__":
    unittest.main()
