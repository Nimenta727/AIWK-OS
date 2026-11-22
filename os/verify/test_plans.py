"""Plan panel model: risk is computed by the platform, text plans are parsed deterministically and marked as parsed."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
import aiws_plans as P
import aiws_cli_adapters as A

PLAN = """I will refactor the auth module safely.

## Steps
1. **Read the current code** in src/auth
   - look at login.py and session.py
   - note the public functions
2. Remove the legacy token table (delete the old migration files)
3. `pip install pyjwt` and update requirements
- Run the tests, then git push to origin
"""

class RiskTests(unittest.TestCase):
    def test_risk_classes(self):
        self.assertEqual(P.risk_of("file.read"), "low"); self.assertEqual(P.risk_of("file.move"), "medium")
        self.assertEqual(P.risk_of("file.trash"), "high"); self.assertEqual(P.risk_of("app.launch"), "high")
        self.assertEqual(P.risk_of("service.restart"), "high"); self.assertEqual(P.risk_of("service.inspect"), "low")
    def test_unknown_tool_is_high_never_low(self):
        self.assertEqual(P.risk_of("totally.new.tool"), "high"); self.assertEqual(P.risk_of(""), "high")

class TextParsing(unittest.TestCase):
    def test_numbered_and_bulleted_steps_with_details_and_goal(self):
        goal, steps = P.parse_text(PLAN)
        self.assertTrue(goal.startswith("I will refactor")); self.assertEqual(len(steps), 4)
        self.assertEqual(steps[0]["title"], "Read the current code in src/auth".replace("in src/auth", "in src/auth"))
        self.assertIn("login.py", steps[0]["detail"]); self.assertTrue(all(s["parsed"] == "text" and s["risk"] == "unknown" for s in steps))
    def test_keyword_hints_are_hints_not_verdicts(self):
        _, steps = P.parse_text(PLAN)
        self.assertIn("delete", steps[1]["hints"]); self.assertIn("install", steps[2]["hints"]); self.assertIn("push", steps[3]["hints"])
        self.assertEqual(steps[0]["hints"], [])
    def test_bounded_and_prose_only_gives_no_steps(self):
        _, steps = P.parse_text("\n".join("%d. step" % i for i in range(1, 200)))
        self.assertEqual(len(steps), P.MAX_STEPS)
        self.assertEqual(P.parse_text("Just some prose without any list.")[1], [])
    def test_secrets_are_redacted_in_titles(self):
        _, steps = P.parse_text("1. set API_KEY=sk-abcdefghijklmnop in env")
        self.assertNotIn("sk-abcdefghijklmnop", steps[0]["title"])

class TodoAndCloud(unittest.TestCase):
    def test_todos_map_states(self):
        plan = P.from_cloud("run1", "todo", [{"content": "Write tests", "status": "completed"}, {"content": "Fix bug", "status": "in_progress"}, {"content": 5}, "x"])
        self.assertEqual([s["state"] for s in plan["steps"]], ["completed", "running"]); self.assertEqual(plan["status"], "running")
        self.assertFalse(plan["parsedFromText"])
    def test_all_completed_is_done(self):
        self.assertEqual(P.from_cloud("r", "todo", [{"content": "a", "status": "completed"}])["status"], "done")
    def test_plan_ids_are_safe(self):
        self.assertRegex(P.from_cloud("../../x y", "text", "1. a")["id"], r"^cloud-[A-Za-z0-9_-]+-text$")

class LocalPlans(unittest.TestCase):
    def stage(self, key, tool, state="pending", approval=0, deps=(), **args):
        return {"stage_key": key, "label": "label " + key, "tool": tool, "arguments": args, "dependsOn": list(deps), "state": state, "approval": approval}
    def test_local_plan_is_normalised_with_platform_risk(self):
        plan = P.from_local({"id": "t1", "title": "Tidy", "goal": "g", "created_at": 1}, [self.stage("a", "file.read", "completed", 1, path="a.txt"), self.stage("b", "file.trash", path="old"), self.stage("c", "file.move", deps=["b"], source="x", destination="y")])
        by = {s["id"]: s for s in plan["steps"]}
        self.assertEqual((by["a"]["risk"], by["b"]["risk"], by["c"]["risk"]), ("low", "high", "medium"))
        self.assertTrue(by["b"]["needsApproval"]); self.assertEqual(by["c"]["deps"], ["b"]); self.assertEqual(by["c"]["targets"], ["x", "y"])
        self.assertEqual(plan["status"], "awaiting-approval")

class StoreTests(unittest.TestCase):
    def test_upsert_replaces_and_is_private_and_bounded(self):
        with tempfile.TemporaryDirectory() as t:
            s = P.PlanStore(Path(t) / "d" / "plans.json")
            s.upsert(P.from_cloud("r", "todo", [{"content": "a", "status": "pending"}])); s.upsert(P.from_cloud("r", "todo", [{"content": "a", "status": "completed"}]))
            self.assertEqual(len(s.list()), 1); self.assertEqual(s.list()[0]["status"], "done")
            self.assertEqual((Path(t) / "d" / "plans.json").stat().st_mode & 0o777, 0o600)
            old = P.MAX_PLANS; P.MAX_PLANS = 3
            try:
                for i in range(6): s.upsert(P.from_cloud("r%d" % i, "todo", [{"content": "x", "status": "pending"}]))
            finally: P.MAX_PLANS = old
            self.assertEqual(len(s.list()), 3)
    def test_corrupt_store_reads_as_empty(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "plans.json"; p.write_text("{not json"); self.assertEqual(P.PlanStore(p).list(), [])

class AdapterHook(unittest.TestCase):
    def test_adapter_collects_plans_without_putting_text_in_events(self):
        a = A.ClaudeStreamAdapter("s1")
        line = json.dumps({"type": "assistant", "message": {"id": "m", "content": [
            {"type": "tool_use", "id": "t1", "name": "TodoWrite", "input": {"todos": [{"content": "SECRET-PLAN-TEXT", "status": "pending"}]}},
            {"type": "tool_use", "id": "t2", "name": "ExitPlanMode", "input": {"plan": "1. do it"}}]}})
        events = a.feed(line)
        self.assertNotIn("SECRET-PLAN-TEXT", json.dumps(events)); got = a.drain_plans()
        self.assertEqual([k for k, _ in got], ["todo", "text"]); self.assertEqual(a.drain_plans(), [])

if __name__ == "__main__":
    unittest.main()
