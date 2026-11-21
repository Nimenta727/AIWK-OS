"""Host-GPU model channel: framing, allowlist, size limits, one-in-flight, loopback-only upstream, no content in logs."""
import io
import json
import os
import struct
import sys
import threading
import time
import unittest
import http.client
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
import aiws_model_channel as M

class Duplex:
    """Two os.pipe pairs presented as one read/write stream each side."""
    def __init__(self, r, w): self.r, self.w = os.fdopen(r, "rb", buffering=0), os.fdopen(w, "wb", buffering=0)
    def read(self, n): return self.r.read(n)
    def write(self, b): return self.w.write(b)
    def flush(self): pass
    def close(self): self.r.close(); self.w.close()

def pair():
    a_r, b_w = os.pipe(); b_r, a_w = os.pipe()
    return Duplex(a_r, a_w), Duplex(b_r, b_w)

class FakeLlama(BaseHTTPRequestHandler):
    seen = []
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b'{"status":"ok"}')
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"])); FakeLlama.seen.append((self.path, body))
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps({"choices": [{"message": {"content": "pong"}}], "echo": len(body)}).encode())

class Rig(unittest.TestCase):
    def setUp(self):
        FakeLlama.seen.clear()
        self.llama = HTTPServer(("127.0.0.1", 0), FakeLlama); threading.Thread(target=self.llama.serve_forever, daemon=True).start()
        self.guest_io, self.host_io = pair(); self.logs = []
        self.host = threading.Thread(target=M.serve_host, args=(self.host_io, "http://127.0.0.1:%d" % self.llama.server_port, lambda *a: self.logs.append(a)), daemon=True)
        self.host.start()
        self.bridge = M.GuestBridge(self.guest_io, lambda *a: self.logs.append(a))
        self.srv = M.make_guest_server(self.bridge, 0); threading.Thread(target=self.srv.serve_forever, daemon=True).start()
    def tearDown(self):
        self.srv.shutdown(); self.srv.server_close(); self.llama.shutdown(); self.llama.server_close()
        for s in (self.guest_io, self.host_io): s.close()
    def http(self, method, path, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_port, timeout=10)
        c.request(method, path, body=body, headers={"Content-Type": "application/json"}); r = c.getresponse(); d = r.read(); c.close()
        return r.status, d

class RoundTrip(Rig):
    def test_chat_round_trip_and_health(self):
        status, data = self.http("POST", "/v1/chat/completions", json.dumps({"messages": [{"role": "user", "content": "ping"}]}))
        self.assertEqual(status, 200); self.assertEqual(json.loads(data)["choices"][0]["message"]["content"], "pong")
        self.assertEqual(self.http("GET", "/health")[0], 200)
    def test_other_paths_and_methods_are_refused_on_the_guest(self):
        for method, path in (("GET", "/v1/files"), ("POST", "/admin"), ("POST", "/health"), ("GET", "/../etc/passwd")):
            self.assertEqual(self.http(method, path, b"{}" if method == "POST" else None)[0], 404, (method, path))
        self.assertEqual(FakeLlama.seen, [])
    def test_host_rechecks_the_allowlist(self):
        M.write_frame(self.guest_io, {"id": 99, "method": "POST", "path": "/admin", "body": "{}"}, 4096)
        self.assertEqual(M.read_frame(self.guest_io, 4096, 5)["status"], 404); self.assertEqual(FakeLlama.seen, [])
    def test_oversized_request_is_rejected_before_the_channel(self):
        status, _ = self.http("POST", "/v1/chat/completions", b"x" * (M.MAX_REQUEST + 10))
        self.assertEqual(status, 413); self.assertEqual(FakeLlama.seen, [])
    def test_logs_contain_sizes_never_prompt_text(self):
        self.http("POST", "/v1/chat/completions", json.dumps({"messages": [{"content": "SECRET-PROMPT-TEXT"}]}))
        self.assertNotIn("SECRET-PROMPT-TEXT", repr(self.logs)); self.assertTrue(self.logs)
    def test_concurrent_calls_are_serialised_not_interleaved(self):
        out = []
        def go(i):
            out.append(self.http("POST", "/v1/chat/completions", json.dumps({"i": i}))[0])
        ts = [threading.Thread(target=go, args=(i,)) for i in range(4)]; [t.start() for t in ts]; [t.join(15) for t in ts]
        self.assertEqual(out, [200] * 4)

class Failures(unittest.TestCase):
    def test_host_down_gives_502_not_a_hang(self):
        g, h = pair(); h.close()                                    # peer vanished
        status, _ = M.GuestBridge(g).call("POST", "/v1/chat/completions", b"{}")
        self.assertEqual(status, 502)
    def test_upstream_down_is_reported(self):
        g, h = pair()
        threading.Thread(target=M.serve_host, args=(h, "http://127.0.0.1:1"), daemon=True).start()
        self.assertEqual(M.GuestBridge(g).call("POST", "/v1/chat/completions", b"{}")[0], 502)
    def test_frame_limits_and_garbage(self):
        buf = io.BytesIO(struct.pack(">I", M.MAX_RESPONSE + 1) + b"x")
        with self.assertRaises(M.ChannelError): M.read_frame(buf, M.MAX_RESPONSE)
        with self.assertRaises(M.ChannelError): M.read_frame(io.BytesIO(struct.pack(">I", 3) + b"abc"), 100)
        with self.assertRaises(M.ChannelError): M.read_frame(io.BytesIO(struct.pack(">I", 2) + b"[]"), 100)
        with self.assertRaises(M.ChannelError): M.write_frame(io.BytesIO(), {"a": "x" * 50}, 10)
    def test_host_only_talks_to_loopback_upstreams(self):
        for ok in ("http://127.0.0.1:8080", "http://localhost:8080"): self.assertTrue(M._upstream_ok(ok), ok)
        for bad in ("http://example.com", "https://127.0.0.1", "http://192.168.1.5:8080", "http://127.0.0.1:8080/admin", "file:///etc/passwd"):
            self.assertFalse(M._upstream_ok(bad), bad)
    def test_response_id_mismatch_is_detected(self):
        g, h = pair()
        def liar():
            M.read_frame(h, 4096, 5); M.write_frame(h, {"id": 12345, "status": 200, "body": "{}"}, 4096)
        threading.Thread(target=liar, daemon=True).start()
        self.assertEqual(M.GuestBridge(g).call("POST", "/v1/chat/completions", b"{}")[0], 502)

if __name__ == "__main__":
    unittest.main()
