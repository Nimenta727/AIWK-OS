"""The DeepSeek agent loop against the SYNTHETIC fake server and the REAL tool plane (confined to a temp project)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "runtime")); sys.path.insert(0, str(HERE / "fixtures"))
import aiws_agent_tree as TREE
import aiws_cloud_agent as A
import aiws_deepseek as D
import aiws_events as E
from fake_deepseek import FakeDeepSeek, KEY, reply, tool_call

def mandate(**kw):
    m = {"projectDir": "app", "allowedTools": ["file.read", "file.replace", "file.trash", "workspace.tree", "code.search", "plan.propose", "plan.update", "agent.spawn"],
         "model": "deepseek-flash", "thinking": True, "effort": "high", "maxTurns": 12, "tokenBudget": {"input": 10 ** 7, "output": 10 ** 6},
         "wallClockMinutes": 5, "needApprovalFor": ["delete", "network", "shell", "outside-project"], "planApproval": True}
    m.update(kw); return m

class Rig(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.proj = Path(self.t.name).resolve() / "app"; self.proj.mkdir()
        (self.proj / "a.txt").write_text("hello"); os.environ["AIWS_WORKSPACE"] = str(self.proj)
        self.out, self.decisions = [], []
    def tearDown(self):
        os.environ.pop("AIWS_WORKSPACE", None); self.t.cleanup()
    def go(self, script, task="do it", **mk):
        fake = FakeDeepSeek(script); self.addCleanup(fake.close); self.fake = fake
        client = D.Client(lambda: KEY, base_url=fake.url, allow_loopback=True, sleep=lambda d: None)
        def read_decision(): return self.decisions.pop(0) if self.decisions else None
        code = A.run({"mandate": mandate(**mk), "task": task, "language": "en"}, self.out.append, read_decision, client)
        return code
    def events(self): return [o for o in self.out if o["t"] == "event"]
    def of(self, t): return [o for o in self.out if o["t"] == t]
    def stored(self):
        """Every event must pass the real event schema."""
        return [E.make_event(1000 + i, "claude", "s1", **{k: v for k, v in e.items() if k != "t"}) for i, e in enumerate(self.events())]

class Basics(Rig):
    def test_plain_answer_events_usage_and_result(self):
        self.assertEqual(self.go([reply("All done.")]), 0)
        kinds = [e["kind"] for e in self.events()]; self.assertEqual((kinds[0], kinds[-1]), ("start", "end"))
        usage = next(e for e in self.events() if e["kind"] == "usage")["tokens"]
        self.assertEqual((usage["source"], usage["scope"]), ("reported", "delta")); self.assertIsNotNone(usage["in"]); self.assertIsNone(usage["cacheWrite"])
        self.assertEqual(self.of("result")[0]["text"], "All done."); self.stored()
    def test_tool_loop_keeps_reasoning_so_the_service_accepts_every_turn(self):
        self.go([reply("", [tool_call("file__read", {"path": "a.txt"})]), reply("", [tool_call("workspace__tree", {})]), reply("The file says hello.")])
        self.assertEqual(self.of("result")[0]["text"], "The file says hello."); self.assertEqual(self.events()[-1]["status"], "ok")
        tools = [(e["tool"], e["status"]) for e in self.events() if e["kind"] == "tool"]
        self.assertEqual(tools[:2], [("file.read", "pending"), ("file.read", "ok")])
        ctx = next(e for e in self.events() if e["kind"] == "tool" and e["tool"] == "file.read" and e["status"] == "pending")["ctx"]; self.assertEqual(ctx, [{"kind": "file", "ref": "a.txt"}])
        for req in self.fake.requests[1:]:
            self.assertTrue(all("reasoning_content" in m for m in req["body"]["messages"] if m["role"] == "assistant"))
        self.stored()
    def test_system_prefix_is_stable_and_tools_sorted_for_prefix_caching(self):
        self.go([reply("", [tool_call("file__read", {"path": "a.txt"})]), reply("ok")])
        r1, r2 = (r["body"] for r in self.fake.requests)
        self.assertEqual(r1["messages"][0], r2["messages"][0]); self.assertEqual(r1["tools"], r2["tools"])
        names = [t["function"]["name"] for t in r1["tools"]]; self.assertEqual(names, sorted(names)); self.assertTrue(all("." not in n for n in names))
    def test_cache_hits_are_reported_not_invented(self):
        self.go([reply("", [tool_call("file__read", {"path": "a.txt"})]), reply("ok")])
        ins = [e["tokens"] for e in self.events() if e["kind"] == "usage"]; self.assertGreater(ins[1]["cacheRead"], 0)
    def test_key_is_never_written_to_the_output(self):
        self.go([reply("", [tool_call("file__read", {"path": "a.txt"})]), reply("ok")]); self.assertNotIn(KEY, json.dumps(self.out))

class Tools(Rig):
    def test_unknown_and_disallowed_tools_get_an_error_reply_not_a_crash(self):
        self.go([reply("", [tool_call("service__restart", {}), tool_call("file__nonexistent", {})]), reply("ok")], allowedTools=["file.read"])
        tool_msgs = [m["content"] for m in self.fake.requests[1]["body"]["messages"] if m["role"] == "tool"]
        self.assertEqual(len(tool_msgs), 2); self.assertTrue(all(t.startswith("error: tool not available") for t in tool_msgs))
    def test_truncated_tool_call_json_is_answered_for_every_call_id(self):
        calls = [tool_call("file__read", None, "c1", raw_args='{"path": "a.t'), tool_call("file__read", {"path": "a.txt"}, "c2")]
        self.go([{"message": reply("", calls)["message"], "finish": "length"}, reply("recovered")])
        msgs = {m["tool_call_id"]: m["content"] for m in self.fake.requests[1]["body"]["messages"] if m["role"] == "tool"}
        self.assertEqual(set(msgs), {"c1", "c2"}); self.assertIn("not valid JSON", msgs["c1"]); self.assertIn("hello", msgs["c2"]); self.assertEqual(self.of("result")[0]["text"], "recovered")
    def test_tool_errors_become_information_for_the_model(self):
        self.go([reply("", [tool_call("file__read", {"path": "../../etc/passwd"})]), reply("ok")])
        content = next(m["content"] for m in self.fake.requests[1]["body"]["messages"] if m["role"] == "tool")
        self.assertTrue(content.startswith("error:")); self.assertIn("error", [e["status"] for e in self.events() if e["kind"] == "tool"])
    def test_huge_tool_output_is_truncated(self):
        (self.proj / "big.txt").write_text("x" * 100000)   # under the tool plane's own 128 KiB file limit, over our output cap
        self.go([reply("", [tool_call("file__read", {"path": "big.txt"})]), reply("ok")])
        content = next(m["content"] for m in self.fake.requests[1]["body"]["messages"] if m["role"] == "tool")
        self.assertLessEqual(len(content), A.MAX_TOOL_OUTPUT + 60); self.assertIn("[truncated", content)
    def test_numbers_in_arguments_are_coerced_not_crashing(self):
        (self.proj / "d").mkdir(); self.go([reply("", [tool_call("workspace__tree", {"path": 5})]), reply("ok")]); self.assertEqual(self.events()[-1]["status"], "ok")

class Gates(Rig):
    def test_delete_waits_for_approval_and_a_refusal_means_nothing_runs(self):
        self.decisions = [{"id": "g1", "approve": False}]
        self.go([reply("", [tool_call("file__trash", {"path": "a.txt", "expectedSha256": "0" * 64})]), reply("ok")])
        g = self.of("gate")[0]; self.assertEqual((g["category"], g["tool"]), ("delete", "file.trash")); self.assertTrue((self.proj / "a.txt").exists())
        self.assertIn("did not approve", next(m["content"] for m in self.fake.requests[1]["body"]["messages"] if m["role"] == "tool"))
        self.assertIn(("file.trash", "denied"), [(e["tool"], e["status"]) for e in self.events() if e["kind"] == "tool"])
    def test_approval_lets_it_run(self):
        import hashlib
        sha = hashlib.sha256(b"hello").hexdigest(); self.decisions = [{"id": "g1", "approve": True}]
        self.go([reply("", [tool_call("file__trash", {"path": "a.txt", "expectedSha256": sha})]), reply("ok")]); self.assertFalse((self.proj / "a.txt").exists())
    def test_no_answer_from_the_supervisor_means_no(self):
        self.go([reply("", [tool_call("file__trash", {"path": "a.txt", "expectedSha256": "0" * 64})]), reply("ok")]); self.assertTrue((self.proj / "a.txt").exists())
    def test_stale_or_foreign_decisions_are_ignored(self):
        self.decisions = [{}, {"id": "g99", "approve": True}, {"id": "g1", "approve": False}]
        self.go([reply("", [tool_call("file__trash", {"path": "a.txt", "expectedSha256": "0" * 64})]), reply("ok")]); self.assertTrue((self.proj / "a.txt").exists())
    def test_writes_only_gated_when_the_mandate_says_so(self):
        self.go([reply("", [tool_call("file__replace", {"path": "n.txt", "text": "hi", "expectedSha256": ""})]), reply("ok")]); self.assertEqual(self.of("gate"), []); self.assertEqual((self.proj / "n.txt").read_text(), "hi")
        self.out.clear(); self.decisions = []
        self.go([reply("", [tool_call("file__replace", {"path": "m.txt", "text": "hi", "expectedSha256": ""})]), reply("ok")], needApprovalFor=["write", "network", "shell", "outside-project"])
        self.assertEqual(self.of("gate")[0]["category"], "write"); self.assertFalse((self.proj / "m.txt").exists())
    def test_path_escape_is_blocked_by_the_tool_plane_even_if_approved(self):
        self.go([reply("", [tool_call("file__replace", {"path": "../evil.txt", "text": "x", "expectedSha256": ""})]), reply("ok")]); self.assertFalse((self.proj.parent / "evil.txt").exists())

class Plans(Rig):
    STEPS = {"title": "Tidy", "goal": "g", "steps": [{"title": "Read it", "tool": "file.read", "targets": ["a.txt"]}, {"title": "Trash it", "tool": "file.trash", "targets": ["a.txt"], "depends_on": [1]}, {"title": "x", "tool": "bogus"}]}
    def test_plan_is_emitted_structured_and_approval_is_returned_to_the_model(self):
        self.decisions = [{"id": "g1", "approve": True}]
        self.go([reply("", [tool_call("plan__propose", self.STEPS)]), reply("", [tool_call("plan__update", {"step": 1, "state": "completed"})]), reply("done")])
        plan = self.of("plan")[0]["plan"]; self.assertEqual([s["tool"] for s in plan["steps"]], ["file.read", "file.trash", None]); self.assertEqual(plan["steps"][1]["deps"], [1])
        self.assertEqual(self.of("gate")[0]["category"], "plan")
        self.assertEqual(json.loads(next(m["content"] for m in self.fake.requests[1]["body"]["messages"] if m["role"] == "tool"))["approved"], True)
        self.assertEqual(self.of("plan_update")[0]["state"], "completed")
    def test_rejected_plan_comes_back_as_a_rejection_and_the_run_continues(self):
        self.decisions = [{"id": "g1", "approve": False}]
        self.assertEqual(self.go([reply("", [tool_call("plan__propose", self.STEPS)]), reply("I will ask what you want.")]), 0)
        self.assertEqual(json.loads(next(m["content"] for m in self.fake.requests[1]["body"]["messages"] if m["role"] == "tool"))["approved"], False)
    def test_plan_approval_can_be_switched_off(self):
        self.go([reply("", [tool_call("plan__propose", self.STEPS)]), reply("go")], planApproval=False); self.assertEqual(self.of("gate"), [])
    def test_malformed_plans_are_rejected_with_an_error(self):
        for bad in ({"title": "", "steps": []}, {"title": "t", "steps": "x"}, {"title": "t", "steps": [{"nope": 1}]}, {"title": "t", "steps": [{"title": "s"}] * 31}):
            self.out.clear(); self.go([reply("", [tool_call("plan__propose", bad)]), reply("ok")])
            self.assertTrue(next(m["content"] for m in self.fake.requests[1]["body"]["messages"] if m["role"] == "tool").startswith("error:"), bad); self.assertEqual(self.of("plan"), [])

class Spawn(Rig):
    def test_sub_agent_events_form_a_tree_with_model_label_context_and_progress(self):
        self.go([reply("", [tool_call("agent__spawn", {"task": "Review a.txt", "label": "Reviewer", "model": "deepseek-v4-pro"})]),
                 reply("", [tool_call("file__read", {"path": "a.txt"})]),       # served to the CHILD (second request)
                 reply("Looks fine."), reply("Parent summary.")])
        by = {n["id"]: n for n in TREE.build([{"seq": i + 1, **e} for i, e in enumerate(self.stored())])["nodes"]}
        n = by["sub-1"]; self.assertEqual((n["parent"], n["label"], n["model"], n["state"]), ("root", "Reviewer", "deepseek-v4-pro", "done"))
        self.assertIn({"kind": "file", "ref": "a.txt"}, n["ctx"]); self.assertIn({"kind": "prompt", "ref": "12 chars"}, n["ctx"]); self.assertEqual(n["tools"], 1)
        self.assertEqual(self.of("result")[0]["text"], "Parent summary.")
        self.assertEqual(self.fake.requests[1]["body"]["model"], "deepseek-v4-pro")
        self.assertEqual(self.fake.requests[1]["body"]["messages"][1]["content"], "Review a.txt")                # fresh context: only the task
    def test_children_cannot_write_unless_allowed_and_can_never_spawn_or_plan(self):
        self.go([reply("", [tool_call("agent__spawn", {"task": "t"})]), reply("x"), reply("ok")])
        names = [t["function"]["name"] for t in self.fake.requests[1]["body"]["tools"]]
        self.assertNotIn("file__replace", names); self.assertNotIn("file__trash", names)
        self.assertTrue({"agent__spawn", "plan__propose", "plan__update"}.isdisjoint(names))
        self.out.clear()
        self.go([reply("", [tool_call("agent__spawn", {"task": "t", "allow_writes": True})]), reply("x"), reply("ok")])
        self.assertIn("file__replace", [t["function"]["name"] for t in self.fake.requests[1]["body"]["tools"]])           # explicit, and only because the mandate allows it
    def test_a_child_can_never_get_a_tool_the_mandate_did_not_grant(self):
        self.go([reply("", [tool_call("agent__spawn", {"task": "t", "allow_writes": True})]), reply("x"), reply("ok")], allowedTools=["file.read", "agent.spawn"])
        self.assertEqual([t["function"]["name"] for t in self.fake.requests[1]["body"]["tools"]], ["file__read"])

    def test_child_count_is_limited(self):
        script = [reply("", [tool_call("agent__spawn", {"task": "t%d" % i}) for i in range(A.MAX_CHILDREN + 2)])] + [reply("c")] * A.MAX_CHILDREN + [reply("ok")]
        self.go(script, maxTurns=100)
        msgs = [m["content"] for m in self.fake.requests[-1]["body"]["messages"] if m["role"] == "tool"]; self.assertEqual(sum(1 for m in msgs if "limit" in m), 2)

class Limits(Rig):
    def test_max_turns_stops_a_looping_model_cleanly(self):
        loop = [reply("", [tool_call("workspace__tree", {})])] * 20
        self.assertEqual(self.go(loop, maxTurns=3), 1); end = self.events()[-1]; self.assertEqual((end["kind"], end["status"], end["detail"]), ("end", "error", "max-turns"))
        self.assertEqual(len(self.fake.requests), 3)
    def test_token_budget_stops_before_overspending(self):
        self.assertEqual(self.go([reply("", [tool_call("workspace__tree", {})], usage_out=4000)] * 5, tokenBudget={"input": 10 ** 7, "output": 5000}), 1)
        self.assertEqual(self.events()[-1]["detail"], "token-budget"); self.assertLessEqual(len(self.fake.requests), 3)
    def test_wall_clock_deadline(self):
        t = [0.0]; fake = FakeDeepSeek([reply("", [tool_call("workspace__tree", {})])] * 5); self.addCleanup(fake.close)
        client = D.Client(lambda: KEY, base_url=fake.url, allow_loopback=True, sleep=lambda d: None)
        def clock(): t[0] += 400; return t[0]
        A.run({"mandate": mandate(wallClockMinutes=5), "task": "x"}, self.out.append, lambda: None, client, clock=clock)
        self.assertEqual(self.events()[-1]["detail"], "time")
    def test_service_failures_end_the_run_with_a_code_and_a_safe_message(self):
        self.assertEqual(self.go([{"status": 402}]), 1); self.assertEqual(self.events()[-1]["detail"], "balance")
        err = next(e for e in self.events() if e["kind"] == "error"); self.assertIn("balance", err["detail"]); self.assertNotIn(KEY, json.dumps(self.out))
    def test_empty_answer_gets_one_nudge(self):
        self.go([reply(""), reply("Now an answer.")]); self.assertEqual(self.of("result")[0]["text"], "Now an answer.")

class Compaction(unittest.TestCase):
    def test_old_tool_results_shrink_but_assistant_turns_are_untouched(self):
        msgs = [{"role": "system", "content": "s"}]
        for i in range(12):
            msgs += [{"role": "assistant", "content": "", "reasoning_content": "r%d" % i, "tool_calls": [{"id": "c%d" % i}]}, {"role": "tool", "tool_call_id": "c%d" % i, "content": "y" * 1000}]
        assistants = [m for m in msgs if m["role"] == "assistant"]; n = A.compact(msgs)
        self.assertEqual(n, 4); self.assertEqual([m for m in msgs if m["role"] == "assistant"], assistants)
        tools = [m["content"] for m in msgs if m["role"] == "tool"]; self.assertTrue(all(t.startswith("[omitted") for t in tools[:4])); self.assertTrue(all(len(t) == 1000 for t in tools[4:]))
        self.assertEqual(A.compact(msgs), 0)                                                                          # idempotent

class Process(Rig):
    """The real entry point: JSON lines over stdin/stdout, gate decisions over stdin."""
    def test_end_to_end_over_pipes(self):
        fake = FakeDeepSeek([reply("", [tool_call("file__trash", {"path": "a.txt", "expectedSha256": "0" * 64})]), reply("finished")]); self.addCleanup(fake.close)
        init = {"t": "init", "key": KEY, "task": "tidy", "mandate": mandate(), "project": str(self.proj), "language": "en"}
        p = subprocess.Popen([sys.executable, str(HERE.parent / "runtime" / "aiws_cloud_agent.py")], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             env={"PATH": os.environ["PATH"], "AIWS_CLOUD_TEST": "1", "AIWS_CLOUD_TEST_URL": fake.url, "PYTHONPATH": str(HERE.parent / "runtime")}, cwd=str(HERE.parent / "runtime"))
        p.stdin.write(json.dumps(init) + "\n"); p.stdin.flush()
        lines = []
        for line in p.stdout:
            o = json.loads(line); lines.append(o)
            if o["t"] == "gate":
                p.stdin.write(json.dumps({"t": "decision", "id": o["id"], "approve": False}) + "\n"); p.stdin.flush()
        p.stdin.close(); p.wait(timeout=30)
        self.assertEqual(p.returncode, 0); self.assertEqual([o["text"] for o in lines if o["t"] == "result"], ["finished"]); self.assertTrue((self.proj / "a.txt").exists())
        self.assertNotIn(KEY, json.dumps(lines)); self.assertNotIn(KEY, p.stderr.read())
    def test_bad_init_exits_2_without_output(self):
        p = subprocess.run([sys.executable, str(HERE.parent / "runtime" / "aiws_cloud_agent.py")], input="garbage\n", capture_output=True, text=True, cwd=str(HERE.parent / "runtime"))
        self.assertEqual((p.returncode, p.stdout), (2, ""))
    def test_test_url_override_is_ignored_unless_explicitly_enabled(self):
        init = {"t": "init", "key": KEY, "task": "x", "mandate": mandate(maxTurns=1), "project": str(self.proj)}
        p = subprocess.run([sys.executable, str(HERE.parent / "runtime" / "aiws_cloud_agent.py")], input=json.dumps(init) + "\n", capture_output=True, text=True, timeout=60,
                           env={"PATH": os.environ["PATH"], "AIWS_CLOUD_TEST_URL": "http://127.0.0.1:1", "PYTHONPATH": str(HERE.parent / "runtime"), "HTTPS_PROXY": "http://127.0.0.1:1"}, cwd=str(HERE.parent / "runtime"))
        self.assertNotIn("127.0.0.1:1", p.stdout.replace("HTTPS_PROXY", ""))   # it tried the real host (and failed to reach it), never the override

if __name__ == "__main__":
    unittest.main()
