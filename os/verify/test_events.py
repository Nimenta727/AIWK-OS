"""O1: aiws.event.v1 schema, tolerant CLI adapters (synthetic fixtures) and the bounded event store."""
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
import aiws_events as ev
from aiws_events import EventError, EventStore, make_event, validate_event, redact
import aiws_cli_adapters as ad
from aiws_cli_adapters import ClaudeStreamAdapter, CodexJsonAdapter, replay

FIX = Path(__file__).resolve().parent / "fixtures" / "cli"

def counter():
    state = iter(range(1, 10 ** 6))
    return lambda: 1700000000.0 + next(state)

class Base(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.store = EventStore(Path(self.t.name) / "events")
    def tearDown(self):
        self.store.close()
        self.t.cleanup()
    def run_fixture(self, name, cls, session):
        return replay(FIX / (name + ".jsonl"), cls(session, counter()), self.store)

class SchemaTests(unittest.TestCase):
    def test_valid_event_roundtrip(self):
        e = make_event(1700000000, "claude", "s1", "usage", tokens={"in": 1, "out": 2, "cacheRead": None, "cacheWrite": None,
                                                                    "source": "reported", "scope": "delta"})
        self.assertEqual(validate_event(e), e)

    def test_invalid_events_are_rejected(self):
        base = {"v": 1, "ts": 1700000000, "agent": "claude", "session": "s", "kind": "message"}
        for bad in ({**base, "v": 2}, {**base, "agent": "gpt"}, {**base, "kind": "boom"}, {**base, "ts": -1},
                    {**base, "ts": True}, {**base, "session": "has space"}, {**base, "session": ""},
                    {**base, "extra": 1}, {**base, "tool": "a b"}, {**base, "status": "great"},
                    {**base, "detail": "x" * 201}, {**base, "detail": "a\nb"},
                    {**base, "tokens": {"in": -1, "source": "reported"}},
                    {**base, "tokens": {"in": True, "source": "reported"}},
                    {**base, "tokens": {"in": 1.5, "source": "reported"}},
                    {**base, "tokens": {"in": 5, "source": "unknown"}},      # unknown must not carry numbers
                    {**base, "tokens": {"source": "reported"}},               # reported needs a number
                    {**base, "tokens": {"in": 1, "source": "estimated"}},
                    {**base, "tokens": {"in": 1, "source": "reported", "scope": "weird"}},
                    {**base, "cost": {"usd": -1, "source": "reported"}}, {**base, "cost": {"usd": 1, "source": "guess"}},
                    "not a dict", None):
            with self.assertRaises(EventError, msg=bad):
                validate_event(bad)

    def test_redaction(self):
        for text in ("export API_KEY=sk-abc123 && npm test", "curl -H 'Authorization: Bearer abcdefgh12345678'", "password: hunter2 go"):
            out = redact(text)
            self.assertNotIn("sk-abc123", out); self.assertNotIn("abcdefgh12345678", out); self.assertNotIn("hunter2", out)
        self.assertEqual(redact("npm test"), "npm test")
        self.assertLessEqual(len(redact("x" * 500)), 120)
        self.assertNotIn("\n", redact("a\nb\x00c"))

class ClaudeAdapterTests(Base):
    def test_basic_stream(self):
        r = self.run_fixture("claude_basic", ClaudeStreamAdapter, "s1")
        self.assertEqual(r["errors"], 0)
        s = self.store.summary("s1")
        self.assertEqual(s["status"], "ok")
        self.assertEqual((s["toolCalls"], s["toolErrors"]), (2, 1))
        self.assertEqual(s["costUsd"], 0.0123)
        # the provider's final TOTAL wins over per-message deltas (and repeated usage was not double counted)
        self.assertEqual({k: s["tokens"][k] for k in ("in", "out", "cacheRead", "cacheWrite")},
                         {"in": 250, "out": 60, "cacheRead": 1100, "cacheWrite": 0})
        self.assertEqual(s["tokens"]["basis"], "reported-total")
        self.assertTrue(s["tokens"]["verified"])

    def test_repeated_message_usage_is_not_double_counted_without_a_total(self):
        a = ClaudeStreamAdapter("s2", counter())
        for line in (Path(FIX / "claude_basic.jsonl").read_text().splitlines()[:6]):   # no result line
            for e in a.feed(line):
                self.store.append(e)
        for e in a.finish():
            self.store.append(e)
        s = self.store.summary("s2")
        self.assertEqual(s["tokens"]["basis"], "sum-of-reported")
        # msg_1 reported the same usage on two lines (100/20/500) and msg_2 150/40/600: 250/60/1100.
        # Without per-message de-duplication this would have been 350/80/1600.
        self.assertEqual((s["tokens"]["in"], s["tokens"]["out"], s["tokens"]["cacheRead"]), (250, 60, 1100))
        self.assertEqual(s["status"], "unknown")        # no result seen -> end is recorded as unknown

    def test_error_result(self):
        self.run_fixture("claude_budget_error", ClaudeStreamAdapter, "s3")
        s = self.store.summary("s3")
        self.assertEqual(s["status"], "error")
        self.assertEqual(self.store.events("s3")[-1]["detail"], "error_max_turns")

    def test_missing_usage_is_unknown_never_zero(self):
        self.run_fixture("claude_no_usage", ClaudeStreamAdapter, "s4")
        t = self.store.summary("s4")["tokens"]
        self.assertEqual((t["in"], t["out"], t["basis"]), (None, None, "none"))
        self.assertGreaterEqual(t["unknownUsageEvents"], 1)

    def test_message_and_tool_text_is_never_stored(self):
        self.run_fixture("claude_basic", ClaudeStreamAdapter, "s5")
        blob = json.dumps(self.store.events("s5"))
        for secret in ("SENTINEL-TEXT-ONE", "SENTINEL-TEXT-TWO", "SENTINEL-TOOL-OUTPUT", "sk-abc123"):
            self.assertNotIn(secret, blob)
        raw = (self.store.folder / "events.sqlite3").read_bytes()
        for secret in (b"SENTINEL-TEXT-ONE", b"sk-abc123"):
            self.assertNotIn(secret, raw)
        details = [e.get("detail") for e in self.store.events("s5")]
        self.assertTrue(any(d and re.fullmatch(r"\d+ chars", d) for d in details))

class CodexAdapterTests(Base):
    def test_basic(self):
        self.run_fixture("codex_basic", CodexJsonAdapter, "c1")
        s = self.store.summary("c1")
        self.assertEqual((s["status"], s["toolCalls"], s["toolErrors"]), ("ok", 2, 0))
        t = s["tokens"]
        self.assertEqual((t["in"], t["out"], t["cacheRead"]), (1200, 90, 800))
        self.assertIsNone(t["cacheWrite"])               # never reported -> unknown, not 0
        self.assertFalse(t["verified"])                  # per-turn semantics unverified: flagged
        blob = json.dumps(self.store.events("c1"))
        for secret in ("SENTINEL-OUTPUT", "SENTINEL-REASONING", "SENTINEL-CODEX-MESSAGE", "abcd1234secret"):
            self.assertNotIn(secret, blob)

    def test_failure(self):
        self.run_fixture("codex_failed", CodexJsonAdapter, "c2")
        s = self.store.summary("c2")
        self.assertEqual((s["status"], s["errors"], s["toolErrors"]), ("error", 1, 1))

    def test_method_params_style(self):
        self.run_fixture("codex_method_style", CodexJsonAdapter, "c3")
        s = self.store.summary("c3")
        self.assertEqual((s["tokens"]["in"], s["tokens"]["out"], s["status"]), (7, 3, "ok"))

    def test_completed_without_started_still_counts_one_call(self):
        a = CodexJsonAdapter("c4", counter())
        events = a.feed(json.dumps({"type": "item.completed", "item": {"id": "z", "type": "command_execution", "exit_code": 0}}))
        self.assertEqual([(e["tool"], e["status"]) for e in events], [("command", "pending"), ("command", "ok")])

class RobustnessTests(Base):
    def test_garbage_never_raises_and_is_counted(self):
        r = self.run_fixture("garbage", ClaudeStreamAdapter, "g1")
        s = self.store.summary("g1")
        self.assertEqual(s["errors"], 2)                       # not-json, array
        self.assertEqual(s["unrecognizedEvents"], 2)           # unknown type, malformed assistant
        self.assertEqual(s["status"], "unknown")
        self.assertEqual(r["lines"], 6)

    def test_oversized_and_binary_lines(self):
        a = ClaudeStreamAdapter("g2", counter())
        self.assertEqual(a.feed("x" * (ad.MAX_LINE + 1))[0]["kind"], "error")
        self.assertEqual(a.feed(b"\xff\xfe{bad")[0]["kind"], "error")
        self.assertEqual(a.feed("   "), [])

    def test_garbage_flood_is_coalesced(self):
        a = ClaudeStreamAdapter("g3", counter())
        produced = sum(len(a.feed("garbage")) for _ in range(1000))
        self.assertLess(produced, 20)

    def test_schema_violations_from_provider_data_do_not_crash(self):
        a = ClaudeStreamAdapter("g4", counter())
        weird = {"type": "assistant", "message": {"id": "m", "content": [
            {"type": "tool_use", "name": "../../etc", "id": 5, "input": {"command": "\x00\x01 x" * 100}}],
            "usage": {"input_tokens": -5, "output_tokens": "many"}}}
        events = a.feed(json.dumps(weird))
        for e in events:
            validate_event(e)                                    # everything emitted is schema-valid
        self.assertFalse(any(e.get("tokens", {}).get("in") == -5 for e in events))

    def test_replay_refuses_symlink_and_huge_files(self):
        link = Path(self.t.name) / "link.jsonl"
        os.symlink(FIX / "claude_basic.jsonl", link)
        with self.assertRaises(EventError):
            replay(link, ClaudeStreamAdapter("x"), self.store)
        big = Path(self.t.name) / "big.jsonl"
        big.write_bytes(b"x" * (ad.MAX_FILE + 1))
        with self.assertRaises(EventError):
            replay(big, ClaudeStreamAdapter("x"), self.store)

class StoreTests(Base):
    def test_summary_precedence_and_unverified_turns(self):
        u = lambda i, **k: make_event(1700000000 + i, "codex", "q", "usage", tokens={"in": k.get("in"), "out": k.get("out"),
                                      "cacheRead": None, "cacheWrite": None, "source": "reported", "scope": k["scope"]})
        self.store.append(u(1, **{"in": 10, "out": 1, "scope": "delta"}))
        self.store.append(u(2, **{"in": 5, "out": 2, "scope": "delta"}))
        s = self.store.summary("q")["tokens"]
        self.assertEqual((s["in"], s["out"], s["basis"], s["verified"]), (15, 3, "sum-of-reported", True))
        self.store.append(u(3, **{"in": 1, "out": 1, "scope": "turn"}))
        s = self.store.summary("q")["tokens"]
        self.assertEqual((s["in"], s["verified"]), (16, False))
        self.store.append(u(4, **{"in": 99, "out": 9, "scope": "total"}))
        s = self.store.summary("q")["tokens"]
        self.assertEqual((s["in"], s["out"], s["basis"]), (99, 9, "reported-total"))

    def test_event_cap_keeps_counters_correct(self):
        with unittest.mock.patch.object(ev, "MAX_EVENTS_PER_SESSION", 5):
            for i in range(12):
                self.store.append(make_event(1700000000 + i, "claude", "cap", "tool", tool="Bash", status="pending"))
        s = self.store.summary("cap")
        self.assertEqual((s["events"], s["toolCalls"], s["truncated"]), (12, 12, True))
        self.assertEqual(len(self.store.events("cap", limit=500)), 5)

    def test_pagination_and_prune(self):
        for n in range(5):
            for i in range(3):
                self.store.append(make_event(1700000000 + n * 10 + i, "claude", "p%d" % n, "message"))
        first = self.store.events("p0", limit=2)
        self.assertEqual(len(first), 2)
        self.assertEqual(len(self.store.events("p0", after=first[-1]["seq"])), 1)
        self.assertEqual([s["session"] for s in self.store.sessions(limit=2)], ["p4", "p3"])
        self.assertEqual(self.store.prune(max_sessions=2), 3)
        self.assertEqual([s["session"] for s in self.store.sessions()], ["p4", "p3"])
        self.assertEqual(self.store.events("p0"), [])
        with self.assertRaises(EventError):
            self.store.summary("p0")

    def test_directory_safety(self):
        link = Path(self.t.name) / "linkdir"
        os.symlink(self.t.name, link)
        with self.assertRaises(EventError):
            EventStore(link)
        with self.assertRaises(EventError):
            EventStore("relative/path")
        mode = (self.store.folder).stat().st_mode & 0o777
        self.assertEqual(mode & 0o077, 0)

    def test_concurrent_appends(self):
        def work(n):
            for i in range(50):
                self.store.append(make_event(1700000000 + i, "claude", "conc", "tool", tool="T%d" % n, status="pending"))
        threads = [threading.Thread(target=work, args=(n,)) for n in range(4)]
        [t.start() for t in threads]; [t.join() for t in threads]
        self.assertEqual(self.store.summary("conc")["toolCalls"], 200)

class IsolationTests(unittest.TestCase):
    def test_modules_have_no_network_or_process_capability(self):
        for name in ("aiws_events.py", "aiws_cli_adapters.py"):
            source = (ROOT / "runtime" / name).read_text(encoding="utf-8")
            for forbidden in ("import socket", "import subprocess", "urllib", "http.client", "os.system", "Popen", "import requests"):
                self.assertNotIn(forbidden, source, name)

    def test_packaged_into_image(self):
        build = build_text()
        for module in ("aiws_events", "aiws_cli_adapters"):
            self.assertIn("os/runtime/" + module + ".py", build)

    def test_fixtures_are_labelled_synthetic(self):
        self.assertIn("SYNTHETIC", (FIX / "README.md").read_text(encoding="utf-8"))
        self.assertIn("not recorded", (FIX / "README.md").read_text(encoding="utf-8").lower().replace("**", ""))

import unittest.mock  # noqa: E402  (used by StoreTests)
from buildsrc import build_text

if __name__ == "__main__":
    unittest.main()
