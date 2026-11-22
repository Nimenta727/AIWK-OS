"""SYNTHETIC DeepSeek server for tests (not the real service). Importable: `FakeDeepSeek(script)`.

It reproduces the documented behaviours that matter to an agent loop:
  * Bearer key check (401);
  * with `tools` and thinking enabled, any earlier assistant message WITHOUT `reasoning_content` -> 400 (the real API does this);
  * `tool_choice` required/named with thinking -> 400;
  * usage with prompt_cache_hit_tokens / prompt_cache_miss_tokens computed from the shared prefix with the previous request;
  * scripted replies: each script entry is consumed in order. Entry forms:
      {"message": {...}, "finish": "stop"|"tool_calls"|"length", "usage_out": 12}   -> 200
      {"status": 429|500|503|402|401|400, "retry_after": "1"}                          -> that error
      {"raw": "<bytes>"}                                                               -> 200 with a raw body
      {"delay": 0.2, "message": ...}                                                   -> slow answer
When the script is exhausted it answers a plain "done".
"""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

KEY = "sk-test-0123456789abcdef"


def tool_call(name, args, ident=None, raw_args=None):
    return {"id": ident or "call_%s_%d" % (name.replace(".", "_"), int(time.time() * 1e6) % 10 ** 6), "type": "function",
            "function": {"name": name, "arguments": raw_args if raw_args is not None else json.dumps(args)}}


def reply(content="", tool_calls=None, reasoning="thinking...", finish=None, usage_out=20):
    m = {"role": "assistant", "content": content}
    if reasoning is not None:
        m["reasoning_content"] = reasoning
    if tool_calls:
        m["tool_calls"] = tool_calls
    return {"message": m, "finish": finish or ("tool_calls" if tool_calls else "stop"), "usage_out": usage_out}


class FakeDeepSeek:
    def __init__(self, script=(), key=KEY):
        self.script, self.key, self.requests, self.lock = list(script), key, [], threading.Lock()
        self.prev_text = ""
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def _send(self, status, obj=None, raw=None, headers=None):
                body = raw if raw is not None else json.dumps(obj).encode()
                self.send_response(status); self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                for k, v in (headers or {}).items(): self.send_header(k, v)
                self.end_headers(); self.wfile.write(body)
            def do_GET(self):
                if self.headers.get("Authorization") != "Bearer " + outer.key: return self._send(401, {"error": {"message": "bad key"}})
                if self.path == "/models": return self._send(200, {"object": "list", "data": [{"id": "deepseek-flash"}, {"id": "deepseek-v4-pro"}]})
                self._send(404, {"error": {"message": "nope"}})
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                with outer.lock: outer.requests.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": body})
                if self.headers.get("Authorization") != "Bearer " + outer.key: return self._send(401, {"error": {"message": "Authentication Fails"}})
                if self.path != "/chat/completions": return self._send(404, {"error": {"message": "nope"}})
                thinking = (body.get("thinking") or {}).get("type", "enabled") == "enabled"
                if thinking and body.get("tools") and any(m.get("role") == "assistant" and "reasoning_content" not in m for m in body["messages"]):
                    return self._send(400, {"error": {"message": "The reasoning_content in the thinking mode must be passed back to the API."}})
                if thinking and body.get("tool_choice") not in (None, "auto", "none"):
                    return self._send(400, {"error": {"message": "tool_choice is not supported in thinking mode"}})
                with outer.lock: step = outer.script.pop(0) if outer.script else reply("done", reasoning="ok")
                if step.get("delay"): time.sleep(step["delay"])
                if "status" in step:
                    return self._send(step["status"], {"error": {"message": "scripted %d" % step["status"]}}, headers={"Retry-After": step["retry_after"]} if "retry_after" in step else None)
                if "raw" in step: return self._send(200, raw=step["raw"] if isinstance(step["raw"], bytes) else step["raw"].encode())
                text = json.dumps(body["messages"], sort_keys=True)
                common = 0
                for a, b in zip(text, outer.prev_text):
                    if a != b: break
                    common += 1
                outer.prev_text = text
                hit, total = common // 4, len(text) // 4
                self._send(200, {"id": "fake-1", "object": "chat.completion", "model": body["model"],
                                 "choices": [{"index": 0, "message": step["message"], "finish_reason": step.get("finish", "stop")}],
                                 "usage": {"prompt_tokens": total, "completion_tokens": step.get("usage_out", 10), "total_tokens": total + step.get("usage_out", 10),
                                           "prompt_cache_hit_tokens": hit, "prompt_cache_miss_tokens": total - hit,
                                           "completion_tokens_details": {"reasoning_tokens": 5}}})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = "http://127.0.0.1:%d" % self.server.server_port

    def close(self):
        self.server.shutdown(); self.server.server_close()
