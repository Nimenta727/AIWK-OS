"""A synthetic OpenAI-compatible model server for tests (stdlib only, loopback only).

It is NOT a model: it answers from a script. It behaves like the servers the client must work with:
  * GET /health (200, 503 while "loading", or the gate's {"gate": true, "loaded": false}), /props, /v1/models
  * POST /v1/chat/completions, plain or streamed (SSE), with llama.cpp style `timings` and OpenAI `usage`
  * can reject optional request fields with HTTP 400 (response_format json_schema, chat_template_kwargs, cache_prompt)
Every request body is kept in `.requests` so tests can assert exactly what was sent.
"""
import json
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def reply(content, finish="stop", usage=(10, 5), timings=None, **extra):
    item = {"content": content, "finish": finish, "usage": usage, "timings": timings}
    item.update(extra)
    return item


class FakeLLM:
    def __init__(self, ctx=8192):
        self.script = deque()
        self.requests = []
        self.reject = set()            # {"json_schema", "chat_template_kwargs", "cache_prompt"} -> HTTP 400
        self.reject_always = False     # every chat request -> 400
        self.reject_message = "unsupported field"   # the text of that error (servers word it freely)
        self.reject_status = 400
        self.no_health = False         # servers without /health (llama-cpp-python, Ollama, LM Studio) answer 404
        self.loading = 0               # this many /health and chat calls answer 503 first
        self.gate_idle = False
        self.ctx = ctx
        self.model_id = "aiws-local"
        self.health_status = 200
        self.lock = threading.Lock()
        outer = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _send(self, code, doc, raw=None):
                data = raw if raw is not None else json.dumps(doc).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if self.path == "/health" and outer.no_health:
                    return self._send(404, {})
                if self.path == "/health":
                    with outer.lock:
                        if outer.loading > 0:
                            outer.loading -= 1
                            return self._send(503, {"error": {"message": "Loading model"}})
                    if outer.health_status != 200:
                        return self._send(outer.health_status, {})
                    return self._send(200, {"gate": True, "loaded": False} if outer.gate_idle else {"status": "ok"})
                if self.path == "/props":
                    return self._send(200, {"default_generation_settings": {"n_ctx": outer.ctx}})
                if self.path == "/v1/models":
                    return self._send(200, {"data": [{"id": outer.model_id}]})
                self._send(404, {})

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                if self.path != "/v1/chat/completions":
                    return self._send(404, {})
                doc = json.loads(body)
                with outer.lock:
                    outer.requests.append(doc)
                    if outer.loading > 0:
                        outer.loading -= 1
                        return self._send(503, {"error": {"message": "Loading model"}})
                    bad = outer.reject_always
                    rf = doc.get("response_format") or {}
                    if "json_schema" in outer.reject and rf.get("type") == "json_schema":
                        bad = True
                    if "json_object_schema" in outer.reject and rf.get("type") == "json_object" and "schema" in rf:
                        bad = True
                    if "json_object" in outer.reject and rf.get("type") == "json_object":
                        bad = True
                    if "chat_template_kwargs" in outer.reject and "chat_template_kwargs" in doc:
                        bad = True
                    if "cache_prompt" in outer.reject and "cache_prompt" in doc:
                        bad = True
                    if "stream_options" in outer.reject and "stream_options" in doc:
                        bad = True
                    if "stream" in outer.reject and doc.get("stream"):
                        bad = True
                    item = None if bad else (outer.script.popleft() if outer.script else reply("{}"))      # a rejected request does not consume a scripted answer
                if bad:
                    return self._send(outer.reject_status, {"error": {"message": outer.reject_message}})
                if callable(item):
                    item = item(doc)
                if item.get("delay"):
                    time.sleep(item["delay"])
                if item.get("status"):
                    return self._send(item["status"], {"error": {"message": "scripted"}})
                if item.get("raw") is not None:
                    return self._send(200, None, raw=item["raw"])
                usage = None if item["usage"] is None else {"prompt_tokens": item["usage"][0], "completion_tokens": item["usage"][1],
                                                            "total_tokens": item["usage"][0] + item["usage"][1]}
                if doc.get("stream"):
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    pieces = item.get("chunks") or [item["content"][i:i + 4] for i in range(0, len(item["content"]), 4)] or [""]
                    try:
                        for p in pieces:
                            self.wfile.write(("data: " + json.dumps({"choices": [{"delta": {"content": p}}]}) + "\n\n").encode())
                            self.wfile.flush()
                            if item.get("chunk_delay"):
                                time.sleep(item["chunk_delay"])
                        last = {"choices": [{"delta": {}, "finish_reason": item["finish"]}]}
                        if usage:
                            last["usage"] = usage
                        if item.get("timings"):
                            last["timings"] = item["timings"]
                        self.wfile.write(("data: " + json.dumps(last) + "\n\ndata: [DONE]\n\n").encode())
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    self.close_connection = True
                    return
                out = {"choices": [{"message": {"role": "assistant", "content": item["content"]}, "finish_reason": item["finish"]}]}
                if usage:
                    out["usage"] = usage
                if item.get("timings"):
                    out["timings"] = item["timings"]
                self._send(200, out)

        class Quiet(ThreadingHTTPServer):
            def handle_error(self, request, client_address):      # a client that gave up (timeout test) is not an error here
                pass

        self.httpd = Quiet(("127.0.0.1", 0), H)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.url = "http://127.0.0.1:%d" % self.port
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *a):
        self.httpd.shutdown()
        self.httpd.server_close()

    def push(self, *items):
        with self.lock:
            self.script.extend(items)
