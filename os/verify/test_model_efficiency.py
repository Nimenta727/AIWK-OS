"""O5: token thrift in the planner (adaptive budget, retry-on-cutoff, result cache, stable prefix, schema opt-in)
and the planner <-> gate contract, with mock / SYNTHETIC servers. No real model is involved."""
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
import aiws_local_model as lm
from aiws_local_model import LocalModelError, LocalPlanner, load_model_config, max_tokens_for, system_prompt
from aiws_model_gate import ModelGate

FAKE = str(Path(__file__).resolve().parent / "fixtures" / "fake_llama.py")
ANSWER = {"tool": "system.info", "arguments": {}, "reason": "check"}

class Mock(BaseHTTPRequestHandler):
    """Scriptable llama-server stand-in. Class-level script: list of (status, finish_reason, content, usage)."""
    requests, script, health = [], [], {"status": "ok"}
    gate_status = {}
    def log_message(self, *a): pass
    def _json(self, status, obj):
        data = json.dumps(obj).encode()
        self.send_response(status); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        Mock.requests.append(("GET", self.path))
        if self.path == "/health":
            return self._json(200, Mock.health)
        if self.path == "/gate/status":
            return self._json(200, Mock.gate_status)
        self._json(404, {})
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        Mock.requests.append(("POST", body))
        status, finish, content, usage = Mock.script.pop(0) if Mock.script else (200, "stop", json.dumps(ANSWER), {"prompt_tokens": 10, "completion_tokens": 5})
        if status != 200:
            return self._json(status, {"error": "x"})
        self._json(200, {"choices": [{"message": {"content": content}, "finish_reason": finish}], "usage": usage})

def posts():
    return [b for m, b in Mock.requests if m == "POST"]

class Base(unittest.TestCase):
    config = {}
    def setUp(self):
        Mock.requests, Mock.script, Mock.health, Mock.gate_status = [], [], {"status": "ok"}, {}
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Mock)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        cfg = {**lm.MODEL_CONFIG_DEFAULT, **self.config}
        self.planner = LocalPlanner(enabled=True, port=self.httpd.server_port, config=cfg)
    def tearDown(self):
        self.httpd.shutdown(); self.httpd.server_close()

class BudgetAndRetryTests(Base):
    def test_budget_follows_the_shape_of_the_request(self):
        for text in ("看看系统信息", "list my files", "move a.txt to docs", "移动 a 到 b"):
            self.assertEqual(max_tokens_for(text), lm.TOKENS_SINGLE, text)
        for text in ("先建文件夹再移动文件", "新建 docs，然后把 a 放进去", "make a folder and then move it", "list files; then delete one", "first check disk, then network"):
            self.assertEqual(max_tokens_for(text), lm.TOKENS_PLAN, text)
        self.planner.suggest("看看系统信息")
        self.planner.suggest("新建 docs，然后把 a 放进去")
        self.assertEqual([p["max_tokens"] for p in posts()], [192, 512])

    def test_cutoff_answer_is_retried_once_with_the_larger_budget_and_usage_is_summed(self):
        Mock.script = [(200, "length", '{"tool": "system.in', {"prompt_tokens": 100, "completion_tokens": 192}),
                       (200, "stop", json.dumps(ANSWER), {"prompt_tokens": 100, "completion_tokens": 20})]
        result = self.planner.suggest("看看系统信息")
        self.assertEqual(result["tool"], "system.info")
        self.assertEqual([p["max_tokens"] for p in posts()], [192, 640])
        self.assertEqual(self.planner.take_usage(), {"in": 200, "out": 212})                  # what was really spent, both attempts
        self.assertTrue(self.planner.take_info()["retried"])

    def test_no_endless_retries(self):
        Mock.script = [(200, "length", '{"tool"', {"prompt_tokens": 1, "completion_tokens": 1})] * 5
        with self.assertRaises(LocalModelError):
            self.planner.suggest("看看系统信息")
        self.assertEqual(len(posts()), 2)                                                      # 192, then 640, then stop

    def test_no_retry_when_the_answer_was_complete(self):
        self.planner.suggest("看看系统信息")
        self.assertEqual(len(posts()), 1)
        self.assertFalse(self.planner.take_info()["retried"])

class PrefixTests(Base):
    def test_request_prefix_is_byte_stable_and_cache_prompt_is_requested(self):
        self.planner.suggest("看看系统信息")
        self.planner.clear_cache()
        self.planner.suggest("list files")
        a, b = posts()
        self.assertEqual(a["messages"][0], b["messages"][0])                                   # identical system message
        self.assertEqual(a["messages"][0]["content"], system_prompt())
        self.assertTrue(a["cache_prompt"] and b["cache_prompt"])
        self.assertNotRegex(a["messages"][0]["content"], r"\d{4}-\d{2}-\d{2}|\d{10}")         # nothing volatile in the prefix
        self.assertEqual(a["messages"][-1], {"role": "user", "content": "看看系统信息"})

    def test_system_prompt_is_stable_across_calls(self):
        self.assertEqual(system_prompt(), system_prompt())
        self.assertEqual(json.dumps(system_prompt()), json.dumps(system_prompt()))

class ResultCacheTests(Base):
    def test_identical_request_and_inventory_cost_no_tokens(self):
        first = self.planner.suggest("看看系统信息")
        self.planner.take_usage(); self.planner.take_info()
        second = self.planner.suggest("看看系统信息")
        self.assertEqual(len(posts()), 1)
        self.assertEqual(first, second)
        self.assertTrue(self.planner.take_info()["cached"])
        self.assertIsNone(self.planner.take_usage())
        second["tool"] = "tampered"                                                             # callers get copies
        self.assertEqual(self.planner.suggest("看看系统信息")["tool"], "system.info")

    def test_a_changed_inventory_or_instruction_is_a_miss(self):
        ctx1 = {"guestFiles": ["a.txt"], "recentTasks": []}
        ctx2 = {"guestFiles": ["a.txt", "b.txt"], "recentTasks": []}
        self.planner.suggest("看看系统信息", ctx1)
        self.planner.suggest("看看系统信息", ctx1)
        self.planner.suggest("看看系统信息", ctx2)
        self.planner.suggest("看看网络状态", ctx1)
        self.assertEqual(len(posts()), 3)
        # only the recent-task list changed (every plan creates a task): still a hit
        before = len(posts())
        self.planner.suggest("看看系统信息", {"guestFiles": ["a.txt"], "recentTasks": [{"id": "t9", "title": "new"}]})
        self.assertEqual(len(posts()), before)

    def test_ttl_disable_lru_and_errors(self):
        short = LocalPlanner(enabled=True, port=self.httpd.server_port, config={**lm.MODEL_CONFIG_DEFAULT, "resultCacheSeconds": 1})
        short.suggest("a1"); short.suggest("a1")
        self.assertEqual(len(posts()), 1)
        time.sleep(1.2)
        short.suggest("a1")
        self.assertEqual(len(posts()), 2)
        Mock.requests.clear()
        off = LocalPlanner(enabled=True, port=self.httpd.server_port, config={**lm.MODEL_CONFIG_DEFAULT, "resultCacheSeconds": 0})
        off.suggest("same"); off.suggest("same")
        self.assertEqual(len(posts()), 2)
        Mock.requests.clear()
        for i in range(lm.RESULT_CACHE_MAX + 5):
            self.planner.suggest("q%d" % i)
        self.assertLessEqual(len(self.planner._cache), lm.RESULT_CACHE_MAX)
        before = len(posts())
        self.planner.suggest("q0")                                                              # evicted: asks again
        self.assertEqual(len(posts()), before + 1)
        Mock.script = [(200, "stop", "not json", {})]
        with self.assertRaises(LocalModelError):
            self.planner.suggest("broken answer")
        Mock.script = []
        n = len(posts())
        self.planner.suggest("broken answer")                                                   # errors are never cached
        self.assertEqual(len(posts()), n + 1)

    def test_refusals_are_cached_too_but_invalid_proposals_are_not(self):
        Mock.script = [(200, "stop", json.dumps({"tool": "refuse", "arguments": {}, "reason": "no"}), {})]
        self.assertEqual(self.planner.suggest("上网下载")["tool"], "refuse")
        self.assertEqual(self.planner.suggest("上网下载")["tool"], "refuse")
        self.assertEqual(len(posts()), 1)
        Mock.script = [(200, "stop", json.dumps({"tool": "host.exec", "arguments": {}, "reason": "x"}), {})]
        with self.assertRaises(LocalModelError):
            self.planner.suggest("bad one")
        self.assertEqual(len(self.planner._cache), 1)

class SchemaModeTests(Base):
    config = {"constrainedOutput": "json_schema"}
    def test_schema_is_sent_and_a_400_falls_back_to_plain_json_for_good(self):
        Mock.script = [(400, "", "", {})]
        result = self.planner.suggest("看看系统信息")
        self.assertEqual(result["tool"], "system.info")
        first, second = posts()
        self.assertEqual(first["response_format"]["type"], "json_schema")
        self.assertEqual(second["response_format"]["type"], "json_object")
        self.assertTrue(self.planner.take_info()["schemaFallback"])
        self.planner.suggest("看看网络状态")
        self.assertEqual(posts()[-1]["response_format"]["type"], "json_object")                # remembered: no more rejected attempts

    def test_schema_mode_when_the_server_accepts_it(self):
        self.planner.suggest("看看系统信息")
        self.assertEqual(posts()[0]["response_format"]["json_schema"]["strict"], True)
        self.assertFalse(self.planner.take_info()["schemaFallback"])

    def test_other_http_errors_do_not_trigger_the_fallback(self):
        Mock.script = [(500, "", "", {})]
        with self.assertRaises(LocalModelError):
            self.planner.suggest("看看系统信息")
        self.assertTrue(self.planner._schema_ok)

    def test_default_is_plain_json_mode(self):
        plain = LocalPlanner(enabled=True, port=self.httpd.server_port, config=dict(lm.MODEL_CONFIG_DEFAULT))
        plain.suggest("x1")
        self.assertEqual(posts()[-1]["response_format"], {"type": "json_object"})

class ConfigTests(unittest.TestCase):
    def test_strict_with_safe_fallbacks(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "model.json"
            self.assertEqual(load_model_config(p), lm.MODEL_CONFIG_DEFAULT)
            p.write_text('{"constrainedOutput": "json_schema", "cachePrompt": false, "resultCacheSeconds": 30}')
            self.assertEqual(load_model_config(p), {"constrainedOutput": "json_schema", "cachePrompt": False, "resultCacheSeconds": 30})
            for bad in ('{"constrainedOutput": "grammar"}', '{"unknown": 1}', '{"resultCacheSeconds": -1}', '{"resultCacheSeconds": 99999}',
                        '{"resultCacheSeconds": true}', "[1]", "{bad", '{"cachePrompt": "yes"}'):
                p.write_text(bad)
                cfg = load_model_config(p)
                self.assertEqual(cfg["constrainedOutput"], "json_object", bad)                 # never silently enables a mode
                self.assertIn(cfg["resultCacheSeconds"], (600,), bad)
            p.unlink(); os.symlink("/etc/passwd", p)
            self.assertEqual(load_model_config(p), lm.MODEL_CONFIG_DEFAULT)
            p.unlink(); p.write_text(" " * 5000)
            self.assertEqual(load_model_config(p), lm.MODEL_CONFIG_DEFAULT)

class StatusTests(Base):
    def test_gate_details_only_when_loaded_and_never_for_a_plain_server(self):
        status = self.planner.status()
        self.assertTrue(status["online"])
        self.assertNotIn("gate", status)                                                       # plain llama-server: no gate block
        Mock.health = {"status": "ok", "gate": True, "loaded": False}
        Mock.requests.clear()
        status = self.planner.status()
        self.assertEqual(status["gate"], {"loaded": False})
        self.assertNotIn(("GET", "/gate/status"), Mock.requests)                               # asking never needs the detail endpoint
        Mock.health = {"status": "ok", "gate": True, "loaded": True}
        Mock.gate_status = {"rssMiB": 1450.5, "peakRssMiB": 1600.0, "lastColdStartSeconds": 7.2, "coldStarts": 2, "idleUnloads": 1, "requests": 9, "secret": "x"}
        status = self.planner.status()
        self.assertEqual(status["gate"]["rssMiB"], 1450.5)
        self.assertNotIn("secret", status["gate"])

def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p

class PlannerThroughGateTests(unittest.TestCase):
    """The planner's real requests must pass the gate's validation, in every mode."""
    def setUp(self):
        self.child_port = free_port()
        self.gate = ModelGate([FAKE, "--host", "127.0.0.1", "--port", str(self.child_port)], listen_port=0, child_port=self.child_port,
                              idle_seconds=0.8, start_timeout=20, allowed_names=("fake_llama.py",))
        self.gate.start()

    def tearDown(self):
        self.gate.close()

    def test_all_modes_work_through_the_gate_and_reports_real_usage(self):
        for mode in ("json_object", "json_schema"):
            planner = LocalPlanner(enabled=True, port=self.gate.port, config={**lm.MODEL_CONFIG_DEFAULT, "constrainedOutput": mode})
            ctx = {"guestFiles": ["a.txt", "docs/"], "recentTasks": [{"id": "t1", "title": "x"}]}
            result = planner.suggest("看看系统信息 " + mode, ctx)
            self.assertEqual(result["tool"], "system.info", mode)
            self.assertEqual(planner.take_usage(), {"in": 100, "out": 10})
            self.assertFalse(planner.take_info()["schemaFallback"], mode)                       # the gate accepted the schema request
            plan = planner.suggest("新建 d，然后移动 a 到 d/a " + mode)
            self.assertEqual(plan["tool"], "system.info")                                       # fake always answers the same

    def test_status_polling_never_loads_the_model_and_unload_is_visible(self):
        planner = LocalPlanner(enabled=True, port=self.gate.port, config=dict(lm.MODEL_CONFIG_DEFAULT))
        for _ in range(5):
            self.assertEqual(planner.status()["gate"], {"loaded": False})
        self.assertEqual(self.gate.status()["coldStarts"], 0)
        planner.suggest("看看系统信息")
        loaded = planner.status()["gate"]
        self.assertTrue(loaded["loaded"])
        self.assertGreater(loaded["rssMiB"], 0)
        for _ in range(60):
            if not self.gate.loaded():
                break
            time.sleep(0.1)
        self.assertEqual(planner.status()["gate"], {"loaded": False})
        self.assertEqual(self.gate.status()["idleUnloads"], 1)

class WorkbenchEventTests(unittest.TestCase):
    def test_cache_hit_is_recorded_as_zero_cost_not_unknown_usage(self):
        import http.client
        from aiws_workbench import make_server, HOST
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Mock)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        Mock.requests, Mock.script = [], []
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); root = base / "ws"; root.mkdir()
            ui = base / "ui"; (ui / "assets").mkdir(parents=True); (ui / "index.html").write_text("<html><head></head><body></body></html>")
            with patch.dict(os.environ, {"AIWS_WORKSPACE": str(root), "XDG_STATE_HOME": str(base / "state")}), \
                    patch("aiws_workbench.load_builder_config", lambda: {"enabled": False, "envAllow": [], "isolation": dict(__import__("aiws_supervisor").ISOLATION_DEFAULT)}), \
                    patch("aiws_workbench.load_config", lambda: {"externalEnabled": False, "providers": {"claude": True, "codex": True}, "extraLocalKeywords": [], "extraExternalKeywords": []}):
                server = make_server(root, ui, 0)
                threading.Thread(target=server.serve_forever, daemon=True).start()
                try:
                    app = server.application
                    app.model = LocalPlanner(enabled=True, port=httpd.server_port, config=dict(lm.MODEL_CONFIG_DEFAULT))
                    def req(method, path, payload=None, headers=None):
                        c = http.client.HTTPConnection(HOST, server.server_port, timeout=10)
                        h = {"Host": HOST + ":" + str(server.server_port), **(headers or {})}
                        if payload is not None:
                            payload = json.dumps(payload); h["Content-Type"] = "application/json"
                        c.request(method, path, body=payload, headers=h); r = c.getresponse(); b = json.loads(r.read()); c.close(); return r.status, b
                    hdr = {"X-AIWS-CSRF": req("GET", "/api/v1/session")[1]["csrf"]}
                    for _ in range(2):
                        self.assertEqual(req("POST", "/api/v1/model/plan", {"instruction": "看看系统信息"}, hdr)[0], 202)
                    time.sleep(0.5)
                    self.assertEqual(len(posts()), 1)                                           # second call never reached the model
                    local = next(s for s in req("GET", "/api/v1/observatory")[1]["sessions"] if s["agent"] == "local")
                    self.assertEqual((local["tokens"]["in"], local["tokens"]["out"]), (10, 5))   # only the real call counted
                    events = req("GET", "/api/v1/observatory/events?session=" + local["session"])[1]["events"]
                    self.assertIn("cache-hit", [e.get("detail") for e in events])
                    self.assertEqual(len([e for e in events if e["kind"] == "usage"]), 1)
                finally:
                    server.shutdown(); server.server_close(); server.application.pool.shutdown(wait=True, cancel_futures=True)
                    time.sleep(0.2); server.application.tasks.close(); server.application.events.close(); server.application.mandates.close()
        httpd.shutdown(); httpd.server_close()

if __name__ == "__main__":
    unittest.main()
