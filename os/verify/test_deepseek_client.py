"""DeepSeek client against the SYNTHETIC fake server: parsing, history rules, retries, error mapping, key hygiene, size caps."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime")); sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures"))
import aiws_deepseek as D
from fake_deepseek import FakeDeepSeek, KEY, reply, tool_call

MSGS = [{"role": "system", "content": "s"}, {"role": "user", "content": "hi"}]
TOOLS = [{"type": "function", "function": {"name": "file.read".replace(".", "_"), "description": "d", "parameters": {"type": "object", "properties": {}}}}]

class Rig(unittest.TestCase):
    def make(self, script=(), key=KEY, **kw):
        self.fake = FakeDeepSeek(script); self.addCleanup(self.fake.close)
        self.sleeps = []
        return D.Client(lambda: key, base_url=self.fake.url, allow_loopback=True, sleep=self.sleeps.append, jitter=lambda: 0.0, **kw)

class Basics(Rig):
    def test_success_parses_message_usage_and_cache_numbers(self):
        c = self.make([reply("hello", usage_out=7)]).chat(MSGS, "deepseek-flash", thinking=False)
        self.assertEqual((c["content"], c["finish"], c["usage"]["out"]), ("hello", "stop", 7))
        self.assertEqual(c["usage"]["cacheHit"] + c["usage"]["cacheMiss"], c["usage"]["in"]); self.assertEqual(c["usage"]["reasoning"], 5)
    def test_request_shape_and_auth_header(self):
        cl = self.make([reply("x")]); cl.chat(MSGS, "deepseek-v4-pro", tools=TOOLS, thinking=True, effort="max", max_tokens=100, user_id="aiws-abc")
        r = self.fake.requests[0]; b = r["body"]
        self.assertEqual(r["auth"], "Bearer " + KEY); self.assertEqual(r["path"], "/chat/completions")
        self.assertEqual((b["model"], b["stream"], b["thinking"], b["reasoning_effort"], b["max_tokens"], b["user_id"]), ("deepseek-v4-pro", False, {"type": "enabled"}, "max", 100, "aiws-abc"))
    def test_thinking_disabled_sends_no_effort(self):
        self.make([reply("x")]).chat(MSGS, "deepseek-flash", thinking=False)
        b = self.fake.requests[0]["body"]; self.assertEqual(b["thinking"], {"type": "disabled"}); self.assertNotIn("reasoning_effort", b)
    def test_tool_calls_are_parsed_and_arguments_stay_a_string(self):
        c = self.make([reply("", [tool_call("file_read", {"path": "a"}, "c1")])]).chat(MSGS, "deepseek-flash", tools=TOOLS)
        self.assertEqual(c["finish"], "tool_calls"); self.assertEqual(c["toolCalls"][0]["id"], "c1"); self.assertIsInstance(c["toolCalls"][0]["function"]["arguments"], str)
    def test_list_models(self):
        self.assertEqual(self.make().list_models(), ["deepseek-flash", "deepseek-v4-pro"])

class HistoryRule(Rig):
    """The real API returns 400 when a past assistant turn lacks reasoning_content (thinking + tools). History must keep it."""
    def test_history_message_keeps_reasoning_and_tool_calls(self):
        c = D.parse_completion({"choices": [{"message": {"role": "assistant", "content": "", "reasoning_content": "r", "tool_calls": [tool_call("file_read", {}, "c1")]}, "finish_reason": "tool_calls"}]})
        m = D.history_message(c); self.assertEqual((m["reasoning_content"], m["tool_calls"][0]["id"]), ("r", "c1"))
    def test_dropping_reasoning_is_rejected_by_the_service_and_keeping_it_works(self):
        cl = self.make([reply("", [tool_call("file_read", {}, "c1")]), reply("ok"), reply("ok2")])
        first = cl.chat(MSGS, "deepseek-flash", tools=TOOLS)
        good = MSGS + [D.history_message(first), {"role": "tool", "tool_call_id": "c1", "content": "data"}]
        self.assertEqual(cl.chat(good, "deepseek-flash", tools=TOOLS)["content"], "ok")
        bad = [dict((k, v) for k, v in m.items() if k != "reasoning_content") for m in good]
        with self.assertRaises(D.DeepSeekError) as cm: cl.chat(bad, "deepseek-flash", tools=TOOLS)
        self.assertEqual((cm.exception.code, cm.exception.retryable), ("bad_request", False))
    def test_required_tool_choice_rejected_in_thinking_mode_before_sending(self):
        cl = self.make()
        with self.assertRaises(D.DeepSeekError): cl.chat(MSGS, "deepseek-flash", tools=TOOLS, tool_choice="required", thinking=True)
        self.assertEqual(self.fake.requests, [])

class Retries(Rig):
    def test_429_then_success_backs_off(self):
        cl = self.make([{"status": 429}, {"status": 503}, reply("ok")]); self.assertEqual(cl.chat(MSGS, "deepseek-flash")["content"], "ok")
        self.assertEqual(cl.retries, 2); self.assertEqual(len(self.sleeps), 2); self.assertGreater(self.sleeps[1], self.sleeps[0])
    def test_retry_after_header_is_honoured_but_capped(self):
        cl = self.make([{"status": 429, "retry_after": "7"}, {"status": 429, "retry_after": "9999"}, reply("ok")]); cl.chat(MSGS, "deepseek-flash")
        self.assertEqual(self.sleeps, [7, 60])
    def test_retries_are_bounded(self):
        cl = self.make([{"status": 500}] * 10, max_retries=2)
        with self.assertRaises(D.DeepSeekError) as cm: cl.chat(MSGS, "deepseek-flash")
        self.assertEqual(cm.exception.code, "server"); self.assertEqual(len(self.fake.requests), 3)
    def test_client_errors_are_not_retried_and_map_to_codes(self):
        for status, code in ((401, "auth"), (402, "balance"), (400, "bad_request"), (422, "bad_request")):
            cl = self.make([{"status": status}])
            with self.assertRaises(D.DeepSeekError) as cm: cl.chat(MSGS, "deepseek-flash")
            self.assertEqual((cm.exception.code, cm.exception.retryable, len(self.fake.requests)), (code, False, 1), status)
    def test_network_failure_is_retryable_then_reported(self):
        cl = D.Client(lambda: KEY, base_url="http://127.0.0.1:1", allow_loopback=True, sleep=lambda d: None, max_retries=1)
        with self.assertRaises(D.DeepSeekError) as cm: cl.chat(MSGS, "deepseek-flash")
        self.assertEqual(cm.exception.code, "network")

class Hygiene(Rig):
    def test_key_never_appears_in_errors(self):
        cl = self.make([{"status": 401}], key=KEY + "x")        # wrong key -> 401 from the fake
        with self.assertRaises(D.DeepSeekError) as cm: cl.chat(MSGS, "deepseek-flash")
        self.assertNotIn(KEY, str(cm.exception)); self.assertNotIn("sk-", str(cm.exception))
    def test_scrub(self):
        self.assertEqual(D.scrub("failed with sk-abcdefgh12345678 here", None), "failed with [key] here"); self.assertNotIn("sk-", D.scrub("a " + KEY, KEY))
    def test_missing_or_malformed_key_is_an_auth_error_without_a_request(self):
        for key in ("", None, "short", "has space in it 12345", "sk-\n12345678"):
            cl = self.make(key=key)
            with self.assertRaises(D.DeepSeekError) as cm: cl.chat(MSGS, "deepseek-flash")
            self.assertEqual(cm.exception.code, "auth")
        self.assertEqual(self.fake.requests, [])
    def test_only_the_official_host_is_accepted(self):
        for bad in ("http://api.deepseek.com", "https://evil.example", "https://api.deepseek.com.evil.example", "https://user@api.deepseek.com", "https://api.deepseek.com/v1", "http://127.0.0.1:9"):
            with self.assertRaises(D.DeepSeekError, msg=bad): D.Client(lambda: KEY, base_url=bad)
        for ok in ("https://api.deepseek.com", "https://api.deepseek.com/", "https://api.deepseek.com/beta"): D.Client(lambda: KEY, base_url=ok)

class Robustness(Rig):
    def test_malformed_responses_are_protocol_errors(self):
        for raw in ("not json", "{}", '{"choices":[]}', '{"choices":[{"message":{"role":"user"}}]}', '{"choices":[{"message":{"role":"assistant","tool_calls":[{"id":1}]}}]}'):
            cl = self.make([{"raw": raw}])
            with self.assertRaises(D.DeepSeekError, msg=raw) as cm: cl.chat(MSGS, "deepseek-flash")
            self.assertEqual(cm.exception.code, "protocol")
    def test_oversized_response_and_request_are_refused(self):
        old = D.MAX_RESPONSE; D.MAX_RESPONSE = 200
        try:
            with self.assertRaises(D.DeepSeekError) as cm: self.make([reply("x" * 500)]).chat(MSGS, "deepseek-flash")
            self.assertEqual(cm.exception.code, "protocol")
        finally: D.MAX_RESPONSE = old
        with self.assertRaises(D.DeepSeekError) as cm: self.make().chat([{"role": "user", "content": "x" * (D.MAX_REQUEST + 1)}], "deepseek-flash")
        self.assertEqual(cm.exception.code, "bad_request")
    def test_unknown_usage_stays_none_not_zero(self):
        u = D.normalise_usage({"prompt_tokens": 5}); self.assertEqual((u["in"], u["out"], u["cacheHit"]), (5, None, None))
        for bad in (None, "x", {"prompt_tokens": -1}, {"prompt_tokens": True}): self.assertIsNone(D.normalise_usage(bad)["in"])
    def test_validation_of_arguments_before_any_request(self):
        cl = self.make()
        for kw in ({"model": "gpt-4"}, {"effort": "extreme"}, {"max_tokens": 0}, {"max_tokens": True}, {"user_id": "bad id!"}, {"tools": [{"type": "function", "function": {"name": "bad name"}}]}):
            args = {"model": "deepseek-flash", **kw}; model = args.pop("model")
            with self.assertRaises(D.DeepSeekError, msg=kw): cl.chat(MSGS, model, **args)
        self.assertEqual(self.fake.requests, [])

if __name__ == "__main__":
    unittest.main()
