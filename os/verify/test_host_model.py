"""Host model supervisor + benchmark: argv building, flag verification, restart backoff, loopback-only bench (no GPU, no real llama)."""
import importlib.util
import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
H = load("aiws_host_model", "host/aiws_host_model.py"); B = load("host_bench", "model/bench/host_bench.py")

HELP = """-m, --model FNAME   model path
--alias STRING --host HOST --port PORT
-c, --ctx-size N
-ngl, --n-gpu-layers N
-fa, --flash-attn [on|off|auto]
-ctk, --cache-type-k TYPE   -ctv, --cache-type-v TYPE
-np, --parallel N
--cache-reuse N
"""

class Argv(unittest.TestCase):
    def test_defaults_bind_loopback_and_use_current_flag_names(self):
        argv = H.build_argv("llama-server", "m.gguf")
        self.assertEqual(argv[argv.index("--host") + 1], "127.0.0.1")
        for f in ("--flash-attn", "--cache-type-k", "--cache-type-v", "--n-gpu-layers", "--parallel", "--cache-reuse", "--ctx-size"): self.assertIn(f, argv)
        self.assertNotIn("--no-mmap", argv)
    def test_overrides_and_validation(self):
        argv = H.build_argv("l", "m", {"ctx": 8192, "cache_k": "f16", "port": 9000}); self.assertEqual(argv[argv.index("--ctx-size") + 1], "8192")
        for bad in ({"flash_attn": "on\n"}, {"ctx": -1}, {"ctx": True}, {"port": 0}, {"port": 70000}, {"flash_attn": "on; rm"}, {"gpu_layers": "a b"}, {"cache_k": ""}):
            with self.assertRaises(ValueError, msg=bad): H.build_argv("l", "m", bad)
        with self.assertRaises(ValueError): H.build_argv("l\n", "m")
    def test_host_is_never_configurable(self):
        argv = H.build_argv("l", "m", {"host": "0.0.0.0"}); self.assertEqual(argv[argv.index("--host") + 1], "127.0.0.1")

class Check(unittest.TestCase):
    def test_all_present(self):
        self.assertEqual(H.missing_flags(HELP, H.build_argv("l", "m")), [])
    def test_renamed_flag_is_reported(self):
        self.assertEqual(H.missing_flags(HELP.replace("--cache-reuse N", ""), H.build_argv("l", "m")), ["--cache-reuse"])
    def test_whole_token_matching(self):
        self.assertIn("--cache-type-k", H.missing_flags("--cache-type-kv", ["--cache-type-k"]))
    def test_check_reports_unrunnable_binary(self):
        bad, why = H.check("/nonexistent/llama-server", ["--x"]); self.assertIsNone(bad); self.assertIn("cannot run", why)

class Supervise(unittest.TestCase):
    class P:
        def __init__(self, code): self.code = code
        def wait(self): return self.code
    def test_restarts_with_growing_then_resetting_backoff(self):
        sleeps, t = [], [0.0]
        def clock(): return t[0]
        def sleep(d): sleeps.append(d)
        def popen(*a, **k):
            t[0] += 0.5; return self.P(1)          # dies after 0.5 s every time
        H.supervise(["x"], popen=popen, sleep=sleep, clock=clock, log=lambda *_: None, max_restarts=5)
        self.assertEqual(sleeps, [2.0, 4.0, 8.0, 16.0, 30.0, 30.0])
    def test_long_uptime_resets_the_delay(self):
        sleeps, t = [], [0.0]
        runs = iter([0.5, 0.5, 120.0, 0.5])
        def popen(*a, **k): t[0] += next(runs); return self.P(0)
        H.supervise(["x"], popen=popen, sleep=sleeps.append, clock=lambda: t[0], log=lambda *_: None, max_restarts=3)
        self.assertEqual(sleeps, [2.0, 4.0, 1.0, 2.0])
    def test_cannot_start_is_survived(self):
        def popen(*a, **k): raise OSError("nope")
        self.assertEqual(H.supervise(["x"], popen=popen, sleep=lambda d: None, log=lambda *_: None, max_restarts=2), 3)

class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        self.send_response(200); self.end_headers()
        self.wfile.write(json.dumps({"usage": {"prompt_tokens": 400, "completion_tokens": 20}}).encode())

class Bench(unittest.TestCase):
    def test_runs_against_a_loopback_server_and_never_invents_numbers(self):
        srv = HTTPServer(("127.0.0.1", 0), Fake); threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            out = B.run("http://127.0.0.1:%d" % srv.server_port, runs=3)
        finally:
            srv.shutdown(); srv.server_close()
        self.assertEqual(out["warm"]["n"], 3); self.assertEqual(out["prefixReuse"]["n"], 3); self.assertEqual(out["cold"]["completionTokens"], 20)
    def test_missing_usage_is_null_not_zero(self):
        rows = [{"seconds": 1.0, "tokensPerSecond": None}]
        self.assertIsNone(B.summarise(rows)["medianTokensPerSecond"])
    def test_cli_refuses_non_loopback(self):
        import subprocess
        p = subprocess.run([sys.executable, str(ROOT / "model/bench/host_bench.py"), "--url", "http://example.com"], capture_output=True, text=True)
        self.assertNotEqual(p.returncode, 0); self.assertIn("loopback", p.stderr + p.stdout)

if __name__ == "__main__":
    unittest.main()
