"""The local agent through the REAL model gate (validation, limits, forwarding) with a scripted stand-in for llama-server as the child.

Why this exists: the gate was written for a one-shot planner (system+user only, at most 8 messages, no streaming, a fixed key list). The agent
sends a conversation with assistant turns, `chat_template_kwargs` and a growing history. A client that passes every unit test against a
permissive fake can still be rejected by the real gate, so this test sends the agent's real requests through it."""
import json
import os
import socket
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
import aiws_llm as L
import aiws_local_agent as A
import aiws_model_gate as mg
import aiws_toolplane as plane

FAKE = str(Path(__file__).resolve().parent / "fixtures" / "fake_llama.py")


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def action(**kw):
    return json.dumps(kw)


class ThroughTheGate(unittest.TestCase):
    def start(self, script):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        base = Path(self.t.name)
        (base / "script.json").write_text(json.dumps(script))
        self.record = base / "requests.jsonl"
        port = free_port()
        argv = [FAKE, "--host", "127.0.0.1", "--port", str(port), "--script", str(base / "script.json"), "--record", str(self.record)]
        self.gate = mg.ModelGate(argv, listen_port=0, child_port=port, idle_seconds=30, start_timeout=20, allowed_names=("fake_llama.py",))
        self.gate.start()
        self.addCleanup(self.gate.close)
        self.invoked = []
        port_obj = A.PlanePort(lambda n, a: (self.invoked.append((n, a)) or {"path": a.get("path"), "text": "hello from " + str(a.get("path"))}), plane.catalog(), plane.READ_TOOLS)
        self.llm = L.LocalLLM("http://127.0.0.1:%d" % self.gate.port, timeout=60, features={"stream": False})
        self.agent = A.LocalAgent(self.llm, port_obj, A.ThreadStore(base / "threads"), skills=__import__("aiws_skills").SkillBook(None, None, None, port_obj.names()))
        return self.agent.store.create()

    def requests(self):
        return [json.loads(l) for l in self.record.read_text().splitlines()]

    def test_a_multi_step_turn_passes_the_gates_validation_and_limits(self):
        tid = self.start([action(type="call", tool="file.read", args={"path": "a.txt"}), action(type="call", tool="file.read", args={"path": "b.txt"}),
                          action(type="call", tool="file.stat", args={"path": "c.txt"}), action(type="final", text="done")])
        r = self.agent.run_turn(tid, "read the file a.txt")
        self.assertEqual((r["outcome"], r["text"]), ("final", "done"))
        self.assertEqual([i[0] for i in self.invoked], ["file.read", "file.read", "file.stat"])
        reqs = self.requests()
        self.assertEqual(len(reqs), 4)
        last = reqs[-1]
        self.assertEqual([m["role"] for m in last["messages"]], ["system", "user", "assistant", "user", "assistant", "user", "assistant", "user"])   # 8 messages, assistant turns included
        self.assertEqual(last["chat_template_kwargs"], {"enable_thinking": False})
        self.assertFalse(last["stream"])
        self.assertEqual(last["response_format"]["type"], "json_schema")
        self.assertEqual(self.llm.features["template_kwargs"], True)                      # the gate accepted it: it was not dropped
        self.assertEqual(r["metrics"]["degraded"], [])

    def test_a_longer_turn_than_the_old_eight_message_limit_works(self):
        script = [action(type="call", tool="file.read", args={"path": "f%d.txt" % i}) for i in range(5)] + [action(type="final", text="ok")]
        tid = self.start(script)
        agent = A.LocalAgent(self.llm, self.agent.port, self.agent.store, skills=self.agent.skills, limits={"maxCalls": 9, "maxSteps": 9})
        r = agent.run_turn(tid, "read the file f0.txt")
        self.assertEqual(r["outcome"], "final")
        self.assertGreater(len(self.requests()[-1]["messages"]), 8)

    def test_streaming_requests_are_refused_by_the_gate_and_the_client_adapts(self):
        tid = self.start([action(type="final", text="plain answer")])
        llm = L.LocalLLM("http://127.0.0.1:%d" % self.gate.port, timeout=60)            # streaming not switched off in advance
        agent = A.LocalAgent(llm, self.agent.port, self.agent.store, skills=self.agent.skills)
        r = agent.run_turn(tid, "hello there")
        self.assertEqual((r["outcome"], r["text"]), ("final", "plain answer"))
        self.assertEqual(r["metrics"]["degraded"], ["stream", "stream_options"])        # learned from the gate's refusals
        self.assertFalse(llm.features["stream"])
        self.assertEqual(self.gate.status()["rejected"], 2)

    def test_the_gate_still_refuses_what_the_agent_never_needs(self):
        self.start([])
        for body in ({"messages": [{"role": "tool", "content": "x"}]}, {"messages": [{"role": "user", "content": "x"}], "tools": []},
                     {"messages": [{"role": "user", "content": "x"}], "chat_template_kwargs": {"enable_thinking": "yes"}},
                     {"messages": [{"role": "assistant", "content": "x"}]}, {"messages": [{"role": "user", "content": "x"}] * 65}):
            with self.assertRaises(L.LLMError, msg=str(body)[:60]) as cm:
                self.llm.chat(body["messages"]) if "tools" not in body and "chat_template_kwargs" not in body else self.llm._post(dict(body, model="aiws-local", max_tokens=8), 10)
            self.assertEqual(cm.exception.kind, "http")


if __name__ == "__main__":
    unittest.main()
