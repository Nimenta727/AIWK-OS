#!/usr/bin/env python3
"""SYNTHETIC stand-in for llama-server, used only by tests.

Flags: --host H --port P [--delay S] (not healthy for S seconds) [--die] (exit immediately) [--busy S] (each chat takes S seconds)
       [--log FILE] (append pid/concurrency events)
"""
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

def arg(name, default=None, cast=str):
    return cast(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default

host, port = arg("--host", "127.0.0.1"), arg("--port", 18081, int)
delay, busy, log = arg("--delay", 0.0, float), arg("--busy", 0.0, float), arg("--log")
if "--die" in sys.argv:
    sys.exit(7)
born = time.time()
state = {"now": 0, "max": 0}
lock = threading.Lock()

def note(event):
    if log:
        with open(log, "a") as f:
            f.write(json.dumps({"event": event, "pid": __import__("os").getpid(), "max": state["max"]}) + "\n")

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send_json(self, status, obj):
        data = json.dumps(obj).encode()
        self.send_response(status); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        if self.path == "/health":
            return self.send_json(200 if time.time() - born >= delay else 503, {"status": "ok" if time.time() - born >= delay else "loading"})
        self.send_json(200, {"leak": "internal endpoint"})
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        with lock:
            state["now"] += 1; state["max"] = max(state["max"], state["now"])
        note("chat")
        time.sleep(busy)
        with lock:
            state["now"] -= 1
        answer = {"tool": "system.info", "arguments": {}, "reason": "fake"}
        self.send_json(200, {"choices": [{"message": {"content": json.dumps(answer)}, "finish_reason": "stop"}],
                             "usage": {"prompt_tokens": 100, "completion_tokens": 10}, "echo_max_tokens": body.get("max_tokens")})

note("start")
ThreadingHTTPServer((host, port), H).serve_forever()
