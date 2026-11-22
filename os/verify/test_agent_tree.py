"""Sub-agent tree: adapter stamps node/parent/ctx from (synthetic, unverified) Claude stream lines; builder never guesses."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
import aiws_agent_tree as T
import aiws_cli_adapters as A
import aiws_events as E

def asst(blocks, parent=None, mid="m1", usage=None):
    m = {"id": mid, "content": blocks}
    if usage: m["usage"] = usage
    return json.dumps({"type": "assistant", "message": m, "parent_tool_use_id": parent})
def tool(name, tid, **inp): return {"type": "tool_use", "id": tid, "name": name, "input": inp}
def result(tid, err=False, parent=None):
    return json.dumps({"type": "user", "parent_tool_use_id": parent, "message": {"content": [{"type": "tool_result", "tool_use_id": tid, "is_error": err}]}})

def run(lines):
    a = A.ClaudeStreamAdapter("s1", clock=iter(range(1000, 2000)).__next__); out = []
    for l in lines: out += a.feed(l)
    out += a.finish(); return [{"seq": i + 1, **e} for i, e in enumerate(out)]

SCRIPT = [
    json.dumps({"type": "system", "subtype": "init", "model": "claude-main-model"}),
    asst([tool("Task", "toolu_A", description="Audit the API", prompt="x" * 400, subagent_type="reviewer", model="claude-sub-model")]),
    asst([tool("Read", "toolu_r1", file_path="src/api.py")], parent="toolu_A", mid="m2", usage={"input_tokens": 10, "output_tokens": 5}),
    asst([tool("Task", "toolu_B", description="Write tests", prompt="go")], parent="toolu_A", mid="m3"),
    asst([tool("Grep", "toolu_g", pattern="TODO")], parent="toolu_B", mid="m4"),
    result("toolu_B", parent="toolu_A"),
    result("toolu_A"),
    asst([tool("Task", "toolu_C", description="Docs", prompt="d")], mid="m5"),
    json.dumps({"type": "result", "subtype": "success", "usage": {"input_tokens": 100, "output_tokens": 50}}),
]

class TreeTests(unittest.TestCase):
    def test_nested_spawns_form_a_tree_with_context_and_state(self):
        t = T.build(run(SCRIPT)); by = {n["id"]: n for n in t["nodes"]}
        self.assertEqual(by["toolu_A"]["parent"], "root"); self.assertEqual(by["toolu_B"]["parent"], "toolu_A")
        self.assertEqual((by["toolu_A"]["depth"], by["toolu_B"]["depth"]), (1, 2))
        self.assertEqual(by["toolu_A"]["label"], "Audit the API [reviewer]"); self.assertEqual(by["toolu_A"]["model"], "claude-sub-model")
        self.assertIn({"kind": "file", "ref": "src/api.py"}, by["toolu_A"]["ctx"]); self.assertIn({"kind": "prompt", "ref": "400 chars"}, by["toolu_A"]["ctx"])
        self.assertIn({"kind": "search", "ref": "TODO"}, by["toolu_B"]["ctx"])
        self.assertEqual((by["toolu_A"]["state"], by["toolu_B"]["state"]), ("done", "done"))
        self.assertEqual(by["toolu_A"]["tokens"]["in"], 10)
    def test_child_without_result_when_stream_ended_is_unknown_not_done(self):
        by = {n["id"]: n for n in T.build(run(SCRIPT))["nodes"]}
        self.assertEqual(by["toolu_C"]["state"], "unknown")
    def test_model_inheritance_is_marked(self):
        by = {n["id"]: n for n in T.build(run(SCRIPT))["nodes"]}
        self.assertEqual(by["toolu_B"]["model"], "claude-sub-model"); self.assertTrue(by["toolu_B"]["modelInherited"])   # from its parent A
        self.assertFalse(by["toolu_A"]["modelInherited"]); self.assertEqual(by["toolu_C"]["model"], "claude-main-model")
    def test_tokens_unknown_stay_none(self):
        by = {n["id"]: n for n in T.build(run(SCRIPT))["nodes"]}
        self.assertIsNone(by["toolu_C"]["tokens"]["in"])
    def test_error_result_marks_error(self):
        lines = [SCRIPT[0], asst([tool("Task", "toolu_X", description="d")]), result("toolu_X", err=True)]
        self.assertEqual({n["id"]: n for n in T.build(run(lines))["nodes"]}["toolu_X"]["state"], "error")
    def test_task_notification_gives_progress(self):
        lines = [SCRIPT[0], asst([tool("Task", "toolu_P", description="d")]),
                 json.dumps({"type": "system", "subtype": "task_notification", "tool_use_id": "toolu_P", "status": "completed", "total_tokens": 900, "tool_uses": 7, "duration_ms": 4200})]
        n = {x["id"]: x for x in T.build(run(lines))["nodes"]}["toolu_P"]
        self.assertEqual((n["state"], n["tools"], n["durationMs"], n["tokens"]["out"]), ("done", 7, 4200, 900))

class RobustnessTests(unittest.TestCase):
    def test_events_for_unseen_nodes_are_attached_to_root_and_flagged(self):
        evs = [{"seq": 1, "ts": 1, "kind": "tool", "tool": "Read", "status": "pending", "node": "ghost"}]
        n = {x["id"]: x for x in T.build(evs)["nodes"]}["ghost"]
        self.assertTrue(n["inferred"]); self.assertEqual(n["parent"], "root")
    def test_cycles_and_self_parent_cannot_hang_or_hide_nodes(self):
        evs = [{"seq": 1, "ts": 1, "kind": "tool", "tool": "Task", "status": "pending", "node": "a", "parent": "b"},
               {"seq": 2, "ts": 2, "kind": "tool", "tool": "Task", "status": "pending", "node": "b", "parent": "a"},
               {"seq": 3, "ts": 3, "kind": "tool", "tool": "Task", "status": "pending", "node": "c", "parent": "c"}]
        t = T.build(evs); self.assertEqual(t["count"], 4)
    def test_node_cap(self):
        evs = [{"seq": i, "ts": i, "kind": "tool", "tool": "Task", "status": "pending", "node": "n%d" % i, "parent": "root"} for i in range(1, 700)]
        t = T.build(evs); self.assertEqual(t["count"], T.MAX_NODES); self.assertGreater(t["droppedNodes"], 0)
    def test_empty(self):
        self.assertEqual(T.build([])["count"], 1)

class SchemaTests(unittest.TestCase):
    def ok(self, **f): return E.make_event(1.0, "claude", "s1", "tool", tool="Task", **f)
    def test_valid_and_invalid_fields(self):
        self.ok(node="toolu_A", parent="root", model="m", label="l", ctx=[{"kind": "file", "ref": "a.py"}], prog={"tools": 1, "ms": 5})
        for bad in ({"node": "has space"}, {"parent": 5}, {"ctx": [{"kind": "x", "ref": "a"}]}, {"ctx": [{"kind": "file", "ref": "a"}] * 9},
                    {"prog": {"tools": -1, "ms": 1}}, {"label": "a\nb"}, {"model": "x" * 61}, {"extra": 1}):
            with self.assertRaises(E.EventError, msg=bad): self.ok(**bad)

if __name__ == "__main__":
    unittest.main()
