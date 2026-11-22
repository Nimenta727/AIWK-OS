"""DeepSeek API client (OpenAI-compatible chat completions). Standard library only; one blocking request at a time.

Facts this module is built on (from api-docs.deepseek.com as read on 2026-11-22; NOT yet exercised against the live service):
  * POST {base}/chat/completions, `Authorization: Bearer <key>`; base https://api.deepseek.com (strict-tool beta: /beta).
  * models: `deepseek-flash`, `deepseek-v4-pro`. The model list changes, so it is configuration, and GET /models can be asked.
  * thinking is ON by default. When the request carries `tools`, the `reasoning_content` of EVERY earlier assistant turn must be
    sent back or the API answers 400, so history keeps the assistant message exactly as returned (see `history_message`).
  * `tool_choice` "required" or a named function is rejected in thinking mode.
  * tool-call `arguments` is a JSON STRING the model may get wrong or truncate (finish_reason "length"): callers must parse it.
  * `usage` reports prompt_cache_hit_tokens / prompt_cache_miss_tokens: real cache numbers, never estimated here.
  * errors: 400/422 fix the request, 401 key, 402 balance, 429 too fast, 500/503 server busy (retry briefly).
Safety rules: the key is fetched per request from a callable, only ever put in the Authorization header, and scrubbed from every
message this module produces; only the official host is accepted (loopback only when a test explicitly allows it); request and
response sizes are capped; retries are bounded with jittered backoff.
"""
import json
import random
import re
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

BASE_URL = "https://api.deepseek.com"
ALLOWED_HOSTS = ("api.deepseek.com",)
MODELS = ("deepseek-flash", "deepseek-v4-pro")
EFFORTS = ("low", "high", "max")
MAX_REQUEST = 8 << 20
MAX_RESPONSE = 16 << 20
RETRY_STATUS = (408, 429, 500, 503)
TOOL_NAME = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")


class DeepSeekError(Exception):
    """`code` is stable (auth, balance, bad_request, rate_limit, server, network, protocol, config); `message` is safe to show."""
    def __init__(self, code, message, status=None, retryable=False):
        super().__init__(message)
        self.code, self.status, self.retryable = code, status, retryable


def scrub(text, key):
    text = str(text)
    if key and len(key) >= 8:
        text = text.replace(key, "[key]")
    return re.sub(r"sk-[A-Za-z0-9]{8,}", "[key]", text)[:300]


def validate_base_url(url, allow_loopback=False):
    u = urlsplit(url)
    ok = (u.scheme == "https" and u.hostname in ALLOWED_HOSTS and u.path.rstrip("/") in ("", "/beta") and not u.query and not u.username)
    if allow_loopback and u.scheme == "http" and u.hostname in ("127.0.0.1", "localhost"):
        ok = True
    if not ok:
        raise DeepSeekError("config", "Only the official DeepSeek API address is allowed")
    return url.rstrip("/")


def normalise_usage(usage):
    """Reported numbers only; a field the service did not send stays None."""
    if not isinstance(usage, dict):
        return {"in": None, "out": None, "cacheHit": None, "cacheMiss": None, "reasoning": None}
    def n(v):
        return v if isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 10 ** 12 else None
    details = usage.get("completion_tokens_details") if isinstance(usage.get("completion_tokens_details"), dict) else {}
    return {"in": n(usage.get("prompt_tokens")), "out": n(usage.get("completion_tokens")), "cacheHit": n(usage.get("prompt_cache_hit_tokens")),
            "cacheMiss": n(usage.get("prompt_cache_miss_tokens")), "reasoning": n(details.get("reasoning_tokens"))}


def validate_tools(tools):
    for t in tools or []:
        f = t.get("function") if isinstance(t, dict) else None
        if (not isinstance(f, dict) or t.get("type") != "function" or not isinstance(f.get("name"), str) or not TOOL_NAME.match(f["name"])
                or not isinstance(f.get("parameters", {}), dict)):
            raise DeepSeekError("config", "Invalid tool definition")


def build_request(messages, model, tools=None, thinking=True, effort="high", max_tokens=None, tool_choice=None, user_id=None, response_format=None):
    if model not in MODELS:
        raise DeepSeekError("config", "Unknown model")
    if effort not in EFFORTS:
        raise DeepSeekError("config", "Unknown reasoning effort")
    validate_tools(tools)
    if tool_choice not in (None, "auto", "none") and thinking:
        raise DeepSeekError("config", "tool_choice other than auto/none is not supported in thinking mode")
    body = {"model": model, "messages": messages, "stream": False,
            "thinking": {"type": "enabled" if thinking else "disabled"}}
    if thinking:
        body["reasoning_effort"] = effort
    if tools:
        body["tools"] = tools
        if tool_choice:
            body["tool_choice"] = tool_choice
    if max_tokens is not None:
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or not 1 <= max_tokens <= 393216:
            raise DeepSeekError("config", "max_tokens out of range")
        body["max_tokens"] = max_tokens
    if user_id is not None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", user_id):
            raise DeepSeekError("config", "Invalid user_id")
        body["user_id"] = user_id
    if response_format:
        body["response_format"] = {"type": "json_object"}
    return body


def parse_completion(data):
    """Normalise one non-streaming response. Raises DeepSeekError('protocol') on anything unexpected."""
    try:
        choice = data["choices"][0]
        msg = choice["message"]
        if msg.get("role") != "assistant":
            raise ValueError
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        raise DeepSeekError("protocol", "The service returned an unexpected response")
    calls = []
    for c in msg.get("tool_calls") or []:
        fn = c.get("function") if isinstance(c, dict) else None
        if not isinstance(fn, dict) or not isinstance(c.get("id"), str) or not isinstance(fn.get("name"), str) or not isinstance(fn.get("arguments", ""), str):
            raise DeepSeekError("protocol", "The service returned a malformed tool call")
        calls.append({"id": c["id"][:128], "type": "function", "function": {"name": fn["name"], "arguments": fn.get("arguments", "")}})
    content = msg.get("content") if isinstance(msg.get("content"), str) else ""
    reasoning = msg.get("reasoning_content") if isinstance(msg.get("reasoning_content"), str) else None
    return {"content": content, "reasoning": reasoning, "toolCalls": calls, "finish": choice.get("finish_reason"),
            "usage": normalise_usage(data.get("usage")), "model": data.get("model") if isinstance(data.get("model"), str) else None,
            "id": data.get("id") if isinstance(data.get("id"), str) else None}


def history_message(c):
    """The assistant message to append to history EXACTLY as the API needs it back (reasoning_content included)."""
    m = {"role": "assistant", "content": c["content"]}
    if c["reasoning"] is not None:
        m["reasoning_content"] = c["reasoning"]
    if c["toolCalls"]:
        m["tool_calls"] = c["toolCalls"]
    return m


def _default_open(request, timeout):
    return urllib.request.urlopen(request, timeout=timeout)


class Client:
    def __init__(self, key_provider, base_url=BASE_URL, opener=None, sleep=time.sleep, jitter=random.random, max_retries=4, timeout=600,
                 allow_loopback=False):
        self.key_provider, self.base = key_provider, validate_base_url(base_url, allow_loopback)
        self.open, self.sleep, self.jitter, self.max_retries, self.timeout = opener or _default_open, sleep, jitter, max_retries, timeout
        self.retries = 0                      # total retries performed (for the run summary)

    def _key(self):
        key = self.key_provider()
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_.\-]{8,256}", key):
            raise DeepSeekError("auth", "No valid DeepSeek API key is configured")
        return key

    def chat(self, messages, model, **kw):
        body = json.dumps(build_request(messages, model, **kw), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(body) > MAX_REQUEST:
            raise DeepSeekError("bad_request", "The conversation is too large to send; it must be shortened")
        key = self._key()
        last = None
        for attempt in range(self.max_retries + 1):
            req = urllib.request.Request(self.base + "/chat/completions", data=body, method="POST",
                                         headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
            try:
                with self.open(req, self.timeout) as resp:
                    raw = resp.read(MAX_RESPONSE + 1)
                if len(raw) > MAX_RESPONSE:
                    raise DeepSeekError("protocol", "The response is too large")
                try:
                    return parse_completion(json.loads(raw.decode("utf-8")))
                except ValueError:
                    raise DeepSeekError("protocol", "The service returned something that is not JSON")
            except urllib.error.HTTPError as exc:
                last = self._http_error(exc, key)
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
            except DeepSeekError:
                raise
            except (OSError, urllib.error.URLError, TimeoutError) as exc:
                last, retry_after = DeepSeekError("network", "Could not reach the DeepSeek API (%s)" % type(exc).__name__, retryable=True), None
            if not last.retryable or attempt >= self.max_retries:
                raise last
            self.retries += 1
            delay = min(2.0 ** attempt, 30.0) * (0.5 + self.jitter() / 2)
            if retry_after and retry_after.isdigit():
                delay = max(delay, min(int(retry_after), 60))
            self.sleep(delay)
        raise last

    @staticmethod
    def _http_error(exc, key):
        try:
            detail = json.loads(exc.read(4096).decode("utf-8", "replace")).get("error", {}).get("message", "")
        except (ValueError, AttributeError, OSError):
            detail = ""
        detail = scrub(detail, key)
        s = exc.code
        table = {401: ("auth", "The API key was rejected"), 402: ("balance", "The DeepSeek account has insufficient balance"),
                 400: ("bad_request", "The request was rejected"), 422: ("bad_request", "The request parameters were rejected"),
                 413: ("bad_request", "The request is too large"), 429: ("rate_limit", "Rate limit reached: too many requests or too much concurrency")}
        code, text = table.get(s, ("server", "The DeepSeek service is busy or failed (HTTP %d)" % s) if s >= 500 else ("bad_request", "Unexpected HTTP %d" % s))
        return DeepSeekError(code, text + (": " + detail if detail and s in (400, 422) else ""), status=s, retryable=s in RETRY_STATUS)

    def list_models(self):
        req = urllib.request.Request(self.base + "/models", headers={"Authorization": "Bearer " + self._key()})
        try:
            with self.open(req, 30) as resp:
                data = json.loads(resp.read(1 << 20).decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc, "")
        except (OSError, ValueError, urllib.error.URLError) as exc:
            raise DeepSeekError("network", "Could not list models (%s)" % type(exc).__name__)
        return [m["id"] for m in data.get("data", []) if isinstance(m, dict) and isinstance(m.get("id"), str)][:50]
