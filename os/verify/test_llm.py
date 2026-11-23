"""Local model client: request shape, graceful degradation, validation, streaming, status, prefix diagnosis. No real model."""
import json
import os
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
sys.path.insert(0, str(ROOT / "verify" / "fixtures"))
import aiws_jsonschema as JS
import aiws_llm as L
from fake_llm import FakeLLM, reply

SCHEMA = {"type": "object", "properties": {"tier": {"enum": ["local", "flash", "pro"]}}, "required": ["tier"], "additionalProperties": False}
MSG = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]


class Endpoint(unittest.TestCase):
    def test_only_loopback_http_is_accepted(self):
        for bad in ("https://127.0.0.1:1", "http://192.168.1.5:80", "http://example.com", "http://user:pw@127.0.0.1:80", "http://127.0.0.1:80/x", "ftp://127.0.0.1"):
            with self.assertRaises(L.LLMError, msg=bad):
                L.LocalLLM(bad)
        L.LocalLLM("http://127.0.0.1:18080"); L.LocalLLM("http://localhost:1"); L.LocalLLM("http://[::1]:1")
        with self.assertRaises(L.LLMError):
            L.LocalLLM("http://127.0.0.1:1", timeout=0)

    def test_environment_proxies_are_never_used(self):
        old = {k: os.environ.get(k) for k in ("http_proxy", "HTTP_PROXY")}
        os.environ["http_proxy"] = os.environ["HTTP_PROXY"] = "http://127.0.0.1:9"          # a dead proxy
        try:
            with FakeLLM() as srv:
                srv.push(reply('{"tier":"pro"}'))
                self.assertEqual(L.LocalLLM(srv.url).chat(MSG)["content"], '{"tier":"pro"}')
        finally:
            for k, v in old.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


class Chat(unittest.TestCase):
    def test_request_shape_and_reported_numbers(self):
        with FakeLLM() as srv:
            srv.push(reply("ok", usage=(120, 7), timings={"cache_n": 100, "prompt_n": 20, "prompt_ms": 400.0, "predicted_n": 7, "predicted_ms": 700.0, "predicted_per_second": 10.0}))
            r = L.LocalLLM(srv.url).chat(MSG, max_tokens=64)
            body = srv.requests[0]
            self.assertEqual((body["model"], body["max_tokens"], body["temperature"], body["stream"]), ("aiws-local", 64, 0.0, False))
            self.assertIs(body["cache_prompt"], True)
            self.assertEqual(body["chat_template_kwargs"], {"enable_thinking": False})
            self.assertNotIn("response_format", body)
            u = r["usage"]
            self.assertEqual((u["promptTokens"], u["completionTokens"], u["cacheN"], u["promptN"], u["tokensPerSecond"], u["source"]), (120, 7, 100, 20, 10.0, "server"))
            self.assertEqual(L.cache_hit_ratio(u), round(100 / 120, 3))

    def test_missing_numbers_stay_none_never_guessed(self):
        with FakeLLM() as srv:
            srv.push(reply("ok", usage=None))
            u = L.LocalLLM(srv.url).chat(MSG)["usage"]
            self.assertEqual(u["source"], "unknown")
            self.assertTrue(all(v is None for k, v in u.items() if k != "source"))
            self.assertIsNone(L.cache_hit_ratio(u))
        self.assertIsNone(L.normalise_usage({"usage": {"prompt_tokens": True, "completion_tokens": -1}})["promptTokens"])
        self.assertIsNone(L.normalise_usage({"usage": {"prompt_tokens": True, "completion_tokens": -1}})["completionTokens"])

    def test_thinking_is_stripped(self):
        self.assertEqual(L.strip_think("<think>plan</think>\n\nanswer"), "answer")
        self.assertEqual(L.strip_think("reasoning only closes</think>answer"), "answer")
        self.assertEqual(L.strip_think("plain"), "plain")

    def test_structured_mode_sends_the_schema(self):
        with FakeLLM() as srv:
            srv.push(reply('{"tier":"flash"}'))
            r = L.LocalLLM(srv.url).chat(MSG, schema=SCHEMA)
            rf = srv.requests[0]["response_format"]
            self.assertEqual((rf["type"], rf["json_schema"]["schema"], rf["json_schema"]["strict"]), ("json_schema", SCHEMA, True))
            self.assertEqual(r["schemaMode"], "json_schema")

    def test_rejected_optional_fields_are_dropped_one_by_one_and_remembered(self):
        with FakeLLM() as srv:
            srv.reject = {"json_schema", "chat_template_kwargs", "cache_prompt"}
            srv.push(reply('{"tier":"flash"}'))
            llm = L.LocalLLM(srv.url)
            r = llm.chat(MSG, schema=SCHEMA)
            self.assertEqual(r["schemaMode"], "json_object_schema")
            self.assertEqual(r["degraded"], ["cache_prompt", "chat_template_kwargs", "response_format:json_object_schema"])
            last = srv.requests[-1]
            self.assertEqual((last["response_format"], "chat_template_kwargs" in last, "cache_prompt" in last), ({"type": "json_object", "schema": SCHEMA}, False, False))
            n = len(srv.requests)
            srv.push(reply('{"tier":"pro"}'))
            llm.chat(MSG, schema=SCHEMA)
            self.assertEqual(len(srv.requests), n + 1)                    # remembered: no new rejected attempts
            self.assertEqual(srv.requests[-1]["response_format"], {"type": "json_object", "schema": SCHEMA})

    def test_an_error_that_names_the_field_drops_only_that_field_whatever_the_status(self):
        with FakeLLM() as srv:
            srv.reject = {"json_schema"}
            srv.reject_status, srv.reject_message = 500, "validation error: loc ('body', 'response_format', 'type') Input should be 'text' or 'json_object'"
            srv.push(reply('{"tier":"flash"}'))
            llm = L.LocalLLM(srv.url)
            r = llm.chat(MSG, schema=SCHEMA)
            self.assertEqual(r["degraded"], ["response_format:json_object_schema"])        # cache_prompt and template kwargs survive
            self.assertTrue(llm.features["cache_prompt"] and llm.features["template_kwargs"])
            self.assertIn("cache_prompt", srv.requests[-1])
            self.assertEqual(blamed := L.blamed_field("unknown field chat_template_kwargs"), "chat_template_kwargs")
            self.assertEqual(L.blamed_field("something else"), None)

    def test_the_ladder_goes_all_the_way_down_to_plain_json_and_remembers_the_floor(self):
        with FakeLLM() as srv:
            srv.reject = {"json_schema", "json_object_schema"}
            srv.reject_message = "response_format not supported"
            srv.push(reply('{"tier":"flash"}'), reply('{"tier":"pro"}'))
            llm = L.LocalLLM(srv.url)
            self.assertEqual(llm.chat(MSG, schema=SCHEMA)["schemaMode"], "json_object")
            n = len(srv.requests)
            self.assertEqual(llm.chat(MSG, schema=SCHEMA)["schemaMode"], "json_object")
            self.assertEqual(len(srv.requests), n + 1)

    def test_a_server_that_rejects_everything_raises_http(self):
        with FakeLLM() as srv:
            srv.reject_always = True
            with self.assertRaises(L.LLMError) as cm:
                L.LocalLLM(srv.url).chat(MSG, schema=SCHEMA)
            self.assertEqual(cm.exception.kind, "http")

    def test_loading_timeout_unreachable_and_size_limits(self):
        with FakeLLM() as srv:
            srv.loading = 1
            with self.assertRaises(L.LLMError) as cm:
                L.LocalLLM(srv.url).chat(MSG)
            self.assertEqual(cm.exception.kind, "loading")
            srv.push(reply("slow", delay=1.6))
            with self.assertRaises(L.LLMError) as cm:
                L.LocalLLM(srv.url, timeout=1).chat(MSG)
            self.assertEqual(cm.exception.kind, "timeout")
            with self.assertRaises(L.LLMError) as cm:
                L.LocalLLM(srv.url).chat([{"role": "user", "content": "x" * (L.MAX_REQUEST + 10)}])
            self.assertEqual(cm.exception.kind, "too_large")
            srv.push(reply("y" * (L.MAX_RESPONSE + 10)))
            with self.assertRaises(L.LLMError) as cm:
                L.LocalLLM(srv.url).chat(MSG)
            self.assertEqual(cm.exception.kind, "too_large")
            srv.push({"raw": b"not json", "usage": None, "content": "", "finish": "stop"})
            with self.assertRaises(L.LLMError) as cm:
                L.LocalLLM(srv.url).chat(MSG)
            self.assertEqual(cm.exception.kind, "invalid_json")
        with self.assertRaises(L.LLMError) as cm:
            L.LocalLLM("http://127.0.0.1:1").chat(MSG)
        self.assertEqual(cm.exception.kind, "unavailable")


class StreamingRefused(unittest.TestCase):
    """The AIWS model gate and the host channel never stream, and the gate rejects `stream_options`: the client must cope, once, and remember."""

    def test_a_server_that_refuses_streaming_gets_a_plain_request_and_it_is_remembered(self):
        with FakeLLM() as srv:
            srv.reject = {"stream_options", "stream"}
            srv.reject_message = "Unsupported request fields"
            srv.push(reply('{"tier":"flash"}'), reply('{"tier":"pro"}'))
            seen = []
            llm = L.LocalLLM(srv.url, timeout=10)
            r = llm.chat(MSG, schema=SCHEMA, on_delta=lambda d: seen.append(d))
            self.assertEqual(r["content"], '{"tier":"flash"}')
            self.assertEqual(r["degraded"], ["stream_options", "stream"])
            self.assertEqual(seen, [])                                              # nothing was streamed, so the callback never ran
            self.assertIsNone(r["timing"]["firstTokenMs"])
            self.assertFalse(srv.requests[-1]["stream"]); self.assertNotIn("stream_options", srv.requests[-1])
            n = len(srv.requests)
            llm.chat(MSG, schema=SCHEMA, on_delta=lambda d: seen.append(d))
            self.assertEqual(len(srv.requests), n + 1)                              # remembered: no new rejected attempts

    def test_a_message_that_names_the_field_is_believed(self):
        with FakeLLM() as srv:
            srv.reject = {"stream"}
            srv.reject_message = "Streaming is not supported"                       # the gate's own wording
            srv.push(reply('{"tier":"flash"}'))
            r = L.LocalLLM(srv.url, timeout=10).chat(MSG, schema=SCHEMA, on_delta=lambda d: None)
            self.assertEqual(r["degraded"], ["stream"])                             # stream_options stayed (nothing named it)
        self.assertEqual((L.blamed_field("unknown field stream_options"), L.blamed_field("Streaming is not supported")), ("stream_options", "stream"))

    def test_streaming_can_be_off_from_the_start(self):
        with FakeLLM() as srv:
            srv.push(reply('{"tier":"flash"}'))
            llm = L.LocalLLM(srv.url, timeout=10, features={"stream": False})
            r = llm.chat(MSG, schema=SCHEMA, on_delta=lambda d: self.fail("must not stream"))
            self.assertEqual((r["degraded"], len(srv.requests), srv.requests[0]["stream"]), ([], 1, False))


class CompleteJson(unittest.TestCase):
    def test_valid_answer_and_fenced_answer(self):
        with FakeLLM() as srv:
            srv.push(reply('{"tier":"pro"}'), reply('```json\n{"tier":"local"}\n```'))
            llm = L.LocalLLM(srv.url)
            self.assertEqual(llm.complete_json(MSG, SCHEMA)[0], {"tier": "pro"})
            self.assertEqual(llm.complete_json(MSG, SCHEMA)[0], {"tier": "local"})

    def test_invalid_answer_gets_one_exact_correction_appended_after_the_conversation(self):
        with FakeLLM() as srv:
            srv.push(reply('{"tier":"huge"}', usage=(50, 5)), reply('{"tier":"pro"}', usage=(70, 5)))
            obj, meta = L.LocalLLM(srv.url).complete_json(MSG, SCHEMA)
            self.assertEqual((obj, meta["repairs"], meta["calls"]), ({"tier": "pro"}, 1, 2))
            second = srv.requests[1]["messages"]
            self.assertEqual(second[:2], MSG)                                    # the stable beginning is untouched
            self.assertIn("$.tier", second[-1]["content"])
            self.assertIn("one of", second[-1]["content"])
            self.assertEqual(second[-2], {"role": "assistant", "content": '{"tier":"huge"}'})
            self.assertEqual(meta["usage"]["promptTokens"], 120)                 # both calls are counted

    def test_still_invalid_after_the_repair_raises_schema_error(self):
        with FakeLLM() as srv:
            srv.push(reply('{"tier":"x"}'), reply('{"tier":"y"}'))
            with self.assertRaises(L.LLMError) as cm:
                L.LocalLLM(srv.url).complete_json(MSG, SCHEMA)
            self.assertEqual(cm.exception.kind, "schema")
            srv.push(reply("nonsense"), reply("still nonsense"))
            with self.assertRaises(L.LLMError) as cm:
                L.LocalLLM(srv.url).complete_json(MSG, SCHEMA)
            self.assertEqual(cm.exception.kind, "invalid_json")

    def test_truncated_answers_are_not_repaired(self):
        with FakeLLM() as srv:
            srv.push(reply('{"tier":"pr', finish="length"))
            with self.assertRaises(L.LLMError) as cm:
                L.LocalLLM(srv.url).complete_json(MSG, SCHEMA)
            self.assertEqual(cm.exception.kind, "truncated")
            self.assertEqual(len(srv.requests), 1)


class Streaming(unittest.TestCase):
    def test_deltas_first_token_time_and_final_numbers(self):
        with FakeLLM() as srv:
            srv.push(reply('{"tier":"flash"}', usage=(30, 6), timings={"cache_n": 0, "prompt_n": 30}, chunk_delay=0.05))
            seen = []
            r = L.LocalLLM(srv.url).chat(MSG, schema=SCHEMA, on_delta=lambda d: seen.append(d))
            self.assertEqual("".join(seen), '{"tier":"flash"}')
            self.assertGreater(len(seen), 2)
            self.assertTrue(srv.requests[0]["stream"])
            self.assertIsNotNone(r["timing"]["firstTokenMs"])
            self.assertLessEqual(r["timing"]["firstTokenMs"], r["timing"]["totalMs"])
            self.assertEqual((r["usage"]["promptTokens"], r["usage"]["promptN"]), (30, 30))
            self.assertEqual(r["finish"], "stop")

    def test_callback_can_cancel_and_a_failing_callback_is_ignored(self):
        with FakeLLM() as srv:
            srv.push(reply("abcdefghijkl", chunk_delay=0.02))
            r = L.LocalLLM(srv.url).chat(MSG, on_delta=lambda d: False)
            self.assertEqual(r["finish"], "cancelled")
            srv.push(reply("abcdefgh"))
            def boom(d):
                raise RuntimeError("ui bug")
            self.assertEqual(L.LocalLLM(srv.url).chat(MSG, on_delta=boom)["content"], "abcdefgh")
            srv.push(reply("abcd", chunk_delay=0.01))
            with self.assertRaises(L.LLMError) as cm:
                L.LocalLLM(srv.url).complete_json(MSG, SCHEMA, on_delta=lambda d: False)
            self.assertEqual(cm.exception.kind, "cancelled")


class Status(unittest.TestCase):
    def test_probe_states(self):
        with FakeLLM(ctx=16384) as srv:
            llm = L.LocalLLM(srv.url)
            p = llm.probe()
            self.assertEqual((p["state"], p["ctx"], p["server"], p["model"]), ("ready", 16384, "llama.cpp", "aiws-local"))
            srv.gate_idle = True
            self.assertEqual(llm.probe()["state"], "idle")
            srv.gate_idle = False; srv.loading = 1
            self.assertEqual(llm.probe()["state"], "loading")
            srv.health_status = 500
            self.assertEqual(llm.probe()["state"], "offline")
        self.assertEqual(L.LocalLLM("http://127.0.0.1:1").probe()["state"], "offline")

    def test_a_server_without_health_is_ready_when_it_lists_models(self):
        with FakeLLM() as srv:
            srv.no_health = True
            p = L.LocalLLM(srv.url).probe()
            self.assertEqual((p["state"], p["model"]), ("ready", "aiws-local"))

    def test_wait_ready_rides_out_the_loading_phase(self):
        with FakeLLM() as srv:
            srv.loading = 2
            t = time.monotonic()
            self.assertEqual(L.LocalLLM(srv.url).wait_ready(5, poll=0.05)["state"], "ready")
            self.assertLess(time.monotonic() - t, 3)
        self.assertEqual(L.LocalLLM("http://127.0.0.1:1").wait_ready(0.2, poll=0.05)["state"], "offline")


class Prefix(unittest.TestCase):
    def test_append_only_is_healthy_and_a_rewrite_names_the_message(self):
        w = L.PrefixWatch()
        a = [{"role": "system", "content": "S"}, {"role": "user", "content": "1"}]
        self.assertTrue(w.observe(a)["appendOnly"])
        b = a + [{"role": "assistant", "content": "x"}, {"role": "user", "content": "2"}]
        r = w.observe(b)
        self.assertEqual((r["appendOnly"], r["reusedMessages"], r["reason"]), (True, 2, "appended"))
        c = [b[0], {"role": "user", "content": "1 (edited)"}] + b[2:]
        r = w.observe(c)
        self.assertEqual((r["appendOnly"], r["firstChanged"], r["role"], r["reusedMessages"]), (False, 1, "user", 1))
        self.assertIn("rewritten", r["reason"])
        r = w.observe([{"role": "system", "content": "S2"}] + c[1:])
        self.assertEqual((r["firstChanged"], r["reason"]), (0, "the system message changed"))
        r = w.observe(c[:2])
        self.assertFalse(r["appendOnly"])

    def test_merge_usage_adds_only_what_was_reported(self):
        a = {"promptTokens": 10, "completionTokens": None}
        b = {"promptTokens": 5, "completionTokens": None, "cacheN": 3}
        m = L.merge_usage(a, b)
        self.assertEqual((m["promptTokens"], m["completionTokens"], m["cacheN"]), (15, None, 3))
        self.assertEqual(L.merge_usage(None, None)["source"], "unknown")

    def test_token_estimate_is_positive_and_scales(self):
        self.assertGreater(L.estimate_tokens("hello world"), 0)
        self.assertGreater(L.estimate_tokens("你好" * 50), L.estimate_tokens("你好"))


class Schema(unittest.TestCase):
    ACTION = {"$defs": {"a": {"type": "object", "properties": {"tool": {"const": "file.read"}, "args": {"type": "object", "properties": {"path": {"type": "string", "pattern": "^[a-z]+$", "maxLength": 5}}, "required": ["path"], "additionalProperties": False}},
                               "required": ["tool", "args"], "additionalProperties": False},
                       "b": {"type": "object", "properties": {"tool": {"const": "refuse"}}, "required": ["tool"], "additionalProperties": False}},
              "oneOf": [{"$ref": "#/$defs/a"}, {"$ref": "#/$defs/b"}]}

    def test_valid_values_pass(self):
        JS.check({"tool": "file.read", "args": {"path": "abc"}}, self.ACTION)
        JS.check({"tool": "refuse"}, self.ACTION)

    def test_errors_name_the_path_and_the_real_problem(self):
        cases = [({"tool": "file.read", "args": {"path": "../x"}}, "$.args.path", "pattern"),
                 ({"tool": "file.read", "args": {"path": "abcdefg"}}, "$.args.path", "longer than 5"),
                 ({"tool": "file.read", "args": {}}, "$.args", "missing required field 'path'"),
                 ({"tool": "file.read", "args": {"path": "a", "extra": 1}}, "$.args", "unexpected field 'extra'"),
                 ({"tool": "refuse", "x": 1}, "$", "unexpected field")]
        for value, path, text in cases:
            with self.assertRaises(JS.SchemaError, msg=str(value)) as cm:
                JS.check(value, self.ACTION)
            self.assertEqual(cm.exception.path, path)
            self.assertIn(text, cm.exception.reason)
        with self.assertRaises(JS.SchemaError) as cm:
            JS.check({"tool": "unknown"}, self.ACTION)
        self.assertIn("does not match any of 2", cm.exception.reason)

    def test_basic_keywords(self):
        for schema, good, bad in (({"type": "integer", "minimum": 1, "maximum": 3}, 2, 0), ({"type": "integer"}, 1, True), ({"type": ["string", "null"]}, None, 1),
                                  ({"enum": ["a", "b"]}, "a", "c"), ({"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 2}, ["a"], []),
                                  ({"const": 1}, 1, True), ({"type": "string", "minLength": 2}, "ab", "a"), ({"type": "object", "maxProperties": 1}, {"a": 1}, {"a": 1, "b": 2})):
            JS.check(good, schema)
            self.assertFalse(JS.is_valid(bad, schema), (schema, bad))
        self.assertTrue(JS.is_valid({"anything": 1}, {"unknownKeyword": True}))

    def test_depth_and_unknown_refs_are_refused(self):
        with self.assertRaises(JS.SchemaError):
            JS.check(1, {"$ref": "#/$defs/missing"}, {"$defs": {}})
        with self.assertRaises(JS.SchemaError):
            JS.check(1, {"$ref": "http://x/y"})
        deep = {"type": "array", "items": None}
        node = deep
        for _ in range(40):
            node["items"] = {"type": "array", "items": None}
            node = node["items"]
        node["items"] = {"type": "integer"}
        value = []
        cur = value
        for _ in range(40):
            nxt = []
            cur.append(nxt)
            cur = nxt
        with self.assertRaises(JS.SchemaError):
            JS.check(value, deep)


if __name__ == "__main__":
    unittest.main()
