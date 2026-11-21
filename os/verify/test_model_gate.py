"""O5: the lazy-start / idle-unload gate, tested with a SYNTHETIC fake llama-server."""
import http.client
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
import aiws_model_gate as mg
from aiws_model_gate import GateError, ModelGate, validate_child_argv, validate_request

FAKE = str(Path(__file__).resolve().parent / "fixtures" / "fake_llama.py")
BODY = {"model": "aiws-local", "messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}], "max_tokens": 64}

def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p

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
    extra = []
    idle = 30.0
    start_timeout = 20.0
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.log = Path(self.t.name) / "fake.log"
        self.child_port = free_port()
        argv = [FAKE, "--host", "127.0.0.1", "--port", str(self.child_port), "--log", str(self.log)] + self.extra
        self.gate = ModelGate(argv, listen_port=0, child_port=self.child_port, idle_seconds=self.idle, start_timeout=self.start_timeout,
                              allowed_names=("fake_llama.py",))
        self.gate.start()

    def tearDown(self):
        self.gate.close(); self.t.cleanup()

    def call(self, method, path, body=None, headers=None, raw=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.gate.port, timeout=60)
        data = raw if raw is not None else (json.dumps(body) if body is not None else None)
        hdr = {"Content-Type": "application/json"} if data is not None else {}
        hdr.update(headers or {})
        conn.request(method, path, body=data, headers=hdr)
        r = conn.getresponse(); payload = r.read(); conn.close()
        try:
            return r.status, json.loads(payload)
        except ValueError:
            return r.status, payload

    def chat(self, **over):
        return self.call("POST", "/v1/chat/completions", {**BODY, **over})

    def events(self):
        return [json.loads(l) for l in self.log.read_text().splitlines()] if self.log.exists() else []

class LifecycleTests(Base):
    def test_health_never_starts_the_model(self):
        for _ in range(5):
            status, h = self.call("GET", "/health")
            self.assertEqual((status, h["status"], h["loaded"]), (200, "ok", False))
        self.assertEqual(self.events(), [])
        self.assertIsNone(self.gate.child)
        self.assertEqual(self.call("GET", "/gate/status")[1]["coldStarts"], 0)

    def test_first_request_starts_it_and_later_ones_reuse_it(self):
        status, out = self.chat()
        self.assertEqual(status, 200)
        self.assertEqual(out["usage"], {"prompt_tokens": 100, "completion_tokens": 10})      # passed through untouched
        s1 = self.call("GET", "/gate/status")[1]
        self.assertTrue(s1["loaded"])
        self.assertEqual((s1["coldStarts"], s1["requests"]), (1, 1))
        self.assertGreater(s1["lastColdStartSeconds"], 0)
        self.assertGreater(s1["rssMiB"], 0)                                                   # a real /proc reading
        self.chat(); self.chat()
        s2 = self.call("GET", "/gate/status")[1]
        self.assertEqual((s2["coldStarts"], s2["requests"], s2["childPid"]), (1, 3, s1["childPid"]))
        self.assertEqual(len([e for e in self.events() if e["event"] == "start"]), 1)
        self.assertTrue(self.call("GET", "/health")[1]["loaded"])

    def test_close_stops_the_child(self):
        self.chat()
        pid = self.gate.status()["childPid"]
        self.assertTrue(alive(pid))
        self.gate.close()
        for _ in range(40):
            if not alive(pid):
                break
            time.sleep(0.05)
        self.assertFalse(alive(pid))

class IdleTests(Base):
    idle = 0.8
    def test_idle_unload_frees_the_process_and_the_next_request_reloads(self):
        self.chat()
        pid = self.gate.status()["childPid"]
        for _ in range(60):
            if not self.gate.loaded():
                break
            time.sleep(0.1)
        self.assertFalse(self.gate.loaded())
        for _ in range(40):
            if not alive(pid):
                break
            time.sleep(0.05)
        self.assertFalse(alive(pid))                                                          # memory really is released
        s = self.call("GET", "/gate/status")[1]
        self.assertEqual((s["loaded"], s["idleUnloads"], s["rssMiB"]), (False, 1, None))
        self.assertEqual(self.chat()[0], 200)
        s = self.call("GET", "/gate/status")[1]
        self.assertEqual((s["coldStarts"], s["idleUnloads"]), (2, 1))
        self.assertNotEqual(s["childPid"], pid)

class BusyTests(Base):
    extra = ["--busy", "2.0"]
    idle = 0.5
    def test_not_unloaded_while_a_request_is_in_flight_and_requests_are_serialised(self):
        results = []
        def go():
            results.append(self.chat()[0])
        threads = [threading.Thread(target=go) for _ in range(2)]
        [t.start() for t in threads]
        time.sleep(1.2)                                                                       # idle (0.5s) has elapsed mid-request
        self.assertTrue(self.gate.loaded())
        [t.join() for t in threads]
        self.assertEqual(results, [200, 200])
        self.assertEqual(max(e["max"] for e in self.events() if e["event"] == "chat"), 1)     # never two at once

class SlowStartTests(Base):
    extra = ["--delay", "1.0"]
    def test_status_and_health_stay_responsive_during_a_cold_start(self):
        done = []
        threading.Thread(target=lambda: done.append(self.chat()[0])).start()
        time.sleep(0.3)
        started = time.time()
        self.assertEqual(self.call("GET", "/health")[0], 200)
        self.assertEqual(self.call("GET", "/gate/status")[0], 200)
        self.assertLess(time.time() - started, 0.5)                                           # not blocked by the model loading
        for _ in range(100):
            if done:
                break
            time.sleep(0.1)
        self.assertEqual(done, [200])

class NeverReadyTests(Base):
    extra = ["--delay", "999"]
    start_timeout = 1.2
    def test_start_timeout_returns_504_and_leaves_nothing_running(self):
        status, out = self.chat()
        self.assertEqual(status, 504)
        self.assertFalse(self.gate.loaded())
        pid_events = [e["pid"] for e in self.events() if e["event"] == "start"]
        for _ in range(40):
            if not any(alive(p) for p in pid_events):
                break
            time.sleep(0.05)
        self.assertFalse(any(alive(p) for p in pid_events))

class CrashTests(Base):
    extra = ["--die"]
    def test_crash_loop_enters_cooldown_instead_of_spinning(self):
        statuses = [self.chat()[0] for _ in range(6)]
        self.assertTrue(all(s == 503 for s in statuses), statuses)
        s = self.call("GET", "/gate/status")[1]
        self.assertGreaterEqual(s["crashes"], 3)
        before = s["crashes"]
        self.chat(); self.chat()
        self.assertEqual(self.call("GET", "/gate/status")[1]["crashes"], before)              # cooling down: no new spawn attempts

class SurvivesKillTests(Base):
    def test_a_killed_child_is_replaced_on_the_next_request(self):
        self.chat()
        pid = self.gate.status()["childPid"]
        os.kill(pid, 9)
        for _ in range(40):
            if not alive(pid):
                break
            time.sleep(0.05)
        self.assertEqual(self.chat()[0], 200)
        self.assertNotEqual(self.gate.status()["childPid"], pid)
        self.assertEqual(self.gate.status()["crashes"], 1)

class RequestValidationTests(Base):
    def test_only_the_three_endpoints_exist(self):
        for method, path in (("GET", "/props"), ("GET", "/slots"), ("GET", "/metrics"), ("POST", "/completion"), ("POST", "/tokenize"),
                             ("GET", "/v1/models"), ("GET", "/"), ("POST", "/health"), ("POST", "/gate/status")):
            self.assertEqual(self.call(method, path, {} if method == "POST" else None)[0], 404, (method, path))
        self.assertEqual(self.events(), [])                                                   # none of them started the model

    def test_bad_requests_are_rejected_before_the_model_is_loaded(self):
        cases = [
            ({"stream": True}, 400), ({"model": "other"}, 400), ({"max_tokens": 5000}, 400), ({"max_tokens": 0}, 400), ({"max_tokens": True}, 400),
            ({"max_tokens": "64"}, 400), ({"temperature": 9}, 400), ({"cache_prompt": "yes"}, 400), ({"messages": []}, 400),
            ({"messages": [{"role": "assistant", "content": "x"}]}, 400), ({"messages": [{"role": "user", "content": "x", "name": "n"}]}, 400),
            ({"messages": [{"role": "user", "content": "x" * 17000}]}, 400), ({"messages": [{"role": "user", "content": "x"}] * 9}, 400),
            ({"grammar": "root ::= x"}, 400), ({"tools": []}, 400), ({"response_format": {"type": "regex"}}, 400), ({"response_format": "json"}, 400),
        ]
        for over, expected in cases:
            self.assertEqual(self.chat(**over)[0], expected, over)
        self.assertEqual(self.call("POST", "/v1/chat/completions", raw="{not json")[0], 400)
        self.assertEqual(self.call("POST", "/v1/chat/completions", raw="[1]")[0], 400)
        self.assertEqual(self.call("POST", "/v1/chat/completions", raw="x" * (mg.MAX_BODY + 1))[0], 413)
        self.assertEqual(self.call("POST", "/v1/chat/completions", raw="", headers={"Content-Length": "0"})[0], 413)
        self.assertEqual(self.call("POST", "/v1/chat/completions", BODY, headers={"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.events(), [])
        self.assertEqual(self.gate.status()["coldStarts"], 0)
        self.assertGreater(self.gate.status()["rejected"], 15)

    def test_valid_options_are_accepted(self):
        ok = self.chat(response_format={"type": "json_schema", "json_schema": {"name": "x", "schema": {"type": "object"}}}, cache_prompt=True, temperature=0.1)
        self.assertEqual(ok[0], 200)
        self.assertEqual(ok[1]["echo_max_tokens"], 64)

class ConstructionTests(unittest.TestCase):
    def test_child_command_is_restricted_to_loopback_llama_server(self):
        good = ["/usr/local/bin/llama-server", "--model", "m.gguf", "--host", "127.0.0.1", "--port", "18081"]
        self.assertEqual(validate_child_argv(good, 18081), good)
        for bad in (["/bin/sh", "--host", "127.0.0.1", "--port", "18081"], good[:3] + ["--host", "0.0.0.0", "--port", "18081"],
                    good[:3] + ["--host", "127.0.0.1", "--port", "18080"], good[:3], [], "llama-server", ["llama-server", 5]):
            with self.assertRaises(GateError, msg=bad):
                validate_child_argv(bad, 18081)

    def test_loopback_only_and_idle_bounds(self):
        with self.assertRaises(GateError):
            ModelGate(["llama-server", "--host", "127.0.0.1", "--port", "1"], child_port=1, idle_seconds=0.01)
        gate = ModelGate(["llama-server", "--host", "127.0.0.1", "--port", "1"], listen_port=0, child_port=1, idle_seconds=60)
        try:
            self.assertEqual(gate.server.server_address[0], "127.0.0.1")
        finally:
            gate.server.server_close()

    def test_request_validator_unit(self):
        self.assertEqual(validate_request(json.dumps(BODY).encode())["max_tokens"], 64)
        with self.assertRaises(GateError):
            validate_request(b'{"messages": 1}')

    def test_source_has_no_shell_and_refuses_root(self):
        src = (ROOT / "runtime/aiws_model_gate.py").read_text(encoding="utf-8")
        self.assertIn("shell=False", src)
        for bad in ("shell=True", "os.system", "import socket", "http.client"):
            self.assertNotIn(bad, src)
        self.assertIn("geteuid", src)

if __name__ == "__main__":
    unittest.main()
