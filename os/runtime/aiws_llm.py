"""Client for the local model's OpenAI-compatible endpoint: the one place that talks to it.

Works with llama.cpp's llama-server (the image), llama-cpp-python's server, vLLM, Ollama and LM Studio, because it only uses what
they have in common: POST /v1/chat/completions with messages, max_tokens, temperature, stream, response_format.
Everything else is OPTIONAL and dropped automatically when a server rejects it:
  response_format json_schema   ->  json_object  ->  nothing   (then our own validator is the only guarantee)
  cache_prompt                  llama.cpp: reuse the KV cache of the previous request (default on there)
  chat_template_kwargs          {"enable_thinking": false}: Qwen3.5 thinks unless told not to; its model card says the old
                                /think and /nothink switches are NOT supported, so this is the portable way to turn it off

Rules this file enforces
  * Loopback only (127.0.0.1 / localhost / ::1), plain http, no proxies. The model never reaches the network and nothing
    off-machine can be configured here.
  * Every number about tokens or time is copied from what the SERVER reported (usage, llama.cpp `timings`). If it did not
    report it, the value is None. Only `estimate_tokens` guesses, and it is named so, for budgeting only.
  * Answers are never trusted: `complete_json` parses and re-validates against the schema, even when the server claims to
    have constrained the output, and can ask the model once to correct itself using the exact validation message.
  * `reasoning_content` (some servers return the model's thinking separately) is dropped and `<think>` blocks are stripped:
    the Qwen3.5 card says history must hold the final answer only.
  * A request that changes the stable beginning of the conversation is reported (`PrefixWatch`), because on a prefix cache that
    is the usual reason an agent suddenly becomes slow. Note this model is a hybrid (a quarter of its layers keep a KV cache, the
    rest are state-space layers): whether the prefix is actually reused is read from `timings.cache_n`, never assumed.
"""
import hashlib
import json
import re
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

import aiws_jsonschema

DEFAULT_URL = "http://127.0.0.1:18080"
MODEL_ALIAS = "aiws-local"
LOOPBACK = ("127.0.0.1", "localhost", "::1")
MAX_RESPONSE = 1 << 20                  # bytes of one reply (a stream is capped at the same total)
MAX_REQUEST = 256 * 1024
THINK = re.compile(r"<think>.*?</think>", re.S)
FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*\Z", re.S)


class LLMError(Exception):
    """kind: unavailable | loading | timeout | http | invalid_json | schema | truncated | too_large | cancelled"""

    def __init__(self, kind, message, detail=""):
        super().__init__(message)
        self.kind = kind
        self.detail = detail


# Structured-output levels, best first. json_schema is the OpenAI form. json_object+schema is llama.cpp's own (also llama-cpp-python's):
# it really constrains decoding, which plain json_object does not (a real 9B answered {"route": ...} when asked for {"tier": ...}).
SCHEMA_MODES = ("json_schema", "json_object_schema", "json_object", "none")


def blamed_field(detail):
    """Which optional request field an error message points at, or None. Servers answer 400, 422 or even 500 and word it freely,
    so we look for the field names instead of guessing from the status."""
    d = (detail or "").lower()
    if any(k in d for k in ("response_format", "json_schema", "json_object", "grammar")):
        return "response_format"
    if "chat_template_kwargs" in d or "enable_thinking" in d:
        return "chat_template_kwargs"
    if "cache_prompt" in d:
        return "cache_prompt"
    if "stream_options" in d:
        return "stream_options"
    if "stream" in d:                                  # "Streaming is not supported" (the AIWS model gate says exactly this)
        return "stream"
    return None


def estimate_tokens(text):
    """A guess for BUDGETING only (never reported as usage): about 3.5 ASCII characters or 0.9 CJK characters per token."""
    cjk = sum(1 for c in text if "⺀" <= c <= "鿿" or "＀" <= c <= "￯")
    return int((len(text) - cjk) / 3.5 + cjk * 0.9) + 1


def strip_think(text):
    text = THINK.sub("", text or "")
    if "</think>" in text:                       # a template that opened the block in the prompt: only the end tag comes back
        text = text.split("</think>", 1)[1]
    return text.strip()


def parse_json_text(text):
    """The model's answer as JSON. Tolerates a ```json fence (servers that cannot constrain output sometimes add one)."""
    text = strip_think(text)
    m = FENCE.match(text)
    if m:
        text = m.group(1)
    try:
        return json.loads(text)
    except ValueError as exc:
        raise LLMError("invalid_json", "The answer is not valid JSON: " + str(exc)[:80])


def _int(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 10 ** 12 else None


def _num(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 10 ** 12 else None


def normalise_usage(response):
    """What the server said about this call. OpenAI `usage` + llama.cpp `timings`; anything missing stays None."""
    usage = response.get("usage") if isinstance(response, dict) and isinstance(response.get("usage"), dict) else {}
    timings = response.get("timings") if isinstance(response, dict) and isinstance(response.get("timings"), dict) else {}
    details = usage.get("prompt_tokens_details") if isinstance(usage.get("prompt_tokens_details"), dict) else {}
    out = {"promptTokens": _int(usage.get("prompt_tokens")), "completionTokens": _int(usage.get("completion_tokens")),
           "cachedTokens": _int(details.get("cached_tokens")),
           "cacheN": _int(timings.get("cache_n")), "promptN": _int(timings.get("prompt_n")), "promptMs": _num(timings.get("prompt_ms")),
           "predictedN": _int(timings.get("predicted_n")), "predictedMs": _num(timings.get("predicted_ms")),
           "tokensPerSecond": _num(timings.get("predicted_per_second"))}
    out["source"] = "server" if any(v is not None for v in out.values()) else "unknown"
    return out


def merge_usage(a, b):
    """Add two reports (a retry, or the steps of a turn). A field is None only if no call reported it."""
    out = {}
    for key in ("promptTokens", "completionTokens", "cachedTokens", "cacheN", "promptN", "promptMs", "predictedN", "predictedMs"):
        x, y = a.get(key) if a else None, b.get(key) if b else None
        out[key] = None if x is None and y is None else (x or 0) + (y or 0)
    out["source"] = "server" if any(v is not None for v in out.values()) else "unknown"
    return out


def cache_hit_ratio(usage):
    """Share of the prompt the server reused, or None when it did not say. llama.cpp: cache_n / (cache_n + prompt_n)."""
    c, p = usage.get("cacheN"), usage.get("promptN")
    if c is None or p is None or c + p == 0:
        return None
    return round(c / (c + p), 3)


def message_hashes(messages):
    return [hashlib.sha256((str(m.get("role")) + "\0" + str(m.get("content"))).encode("utf-8")).hexdigest()[:16] for m in messages]


class PrefixWatch:
    """Compares each request with the previous one of the same conversation and says what changed at the front.

    A healthy agent only APPENDS. If an earlier message changed, a prefix cache cannot reuse anything after it, and this tells
    you which message (index and role), so the cause can be found instead of guessed (tool list reordered, a timestamp put
    into the system message, history rewritten by compaction ...)."""

    def __init__(self):
        self.prev = []
        self.prev_roles = []

    def observe(self, messages):
        cur = message_hashes(messages)
        roles = [str(m.get("role")) for m in messages]
        if not self.prev:
            report = {"appendOnly": True, "firstChanged": None, "reusedMessages": 0, "reason": "first request"}
        else:
            n = min(len(self.prev), len(cur))
            first = next((i for i in range(n) if self.prev[i] != cur[i]), None)
            if first is None and len(cur) < len(self.prev):
                first = len(cur)
            if first is None:
                report = {"appendOnly": True, "firstChanged": None, "reusedMessages": len(self.prev), "reason": "appended"}
            else:
                why = "the system message changed" if first == 0 else (
                    "history became shorter (compaction or retry?)" if len(cur) < len(self.prev) else "an earlier message was rewritten")
                report = {"appendOnly": False, "firstChanged": first, "role": roles[first] if first < len(roles) else None,
                          "reusedMessages": first, "reason": why}
        self.prev, self.prev_roles = cur, roles
        return report


class LocalLLM:
    def __init__(self, base_url=DEFAULT_URL, model=MODEL_ALIAS, timeout=120, opener=None, features=None):
        parts = urlsplit(base_url)
        if parts.scheme != "http" or parts.hostname not in LOOPBACK or parts.username or parts.password or parts.path not in ("", "/"):
            raise LLMError("unavailable", "The local model endpoint must be http on the loopback address")
        if not isinstance(timeout, (int, float)) or not 1 <= timeout <= 1800:
            raise LLMError("unavailable", "Invalid timeout")
        host = "[::1]" if parts.hostname == "::1" else parts.hostname
        self.base = "http://%s:%d" % (host, parts.port or 80)
        self.model = model
        self.timeout = timeout
        self.opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}))     # never through a proxy
        # Optional request fields. Turned off for the life of this object when a server rejects them.
        self.features = {"cache_prompt": True, "template_kwargs": True, "stream": True, "stream_options": True}
        self.mode_floor = 0            # index into SCHEMA_MODES of the best structured-output level believed to work
        if features:
            self.features.update({k: v for k, v in features.items() if k in self.features})
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ status
    def _get(self, path, timeout=3):
        try:
            with self.opener.open(urllib.request.Request(self.base + path, method="GET"), timeout=timeout) as r:
                return r.status, r.read(65536)
        except urllib.error.HTTPError as exc:
            return exc.code, b""
        except (urllib.error.URLError, TimeoutError, OSError):
            return None, b""

    def probe(self):
        """{"state": ready|loading|idle|offline, "ctx": per-slot context or None, ...}. Asking never loads the model."""
        status, body = self._get("/health")
        info = {"state": "offline", "ctx": None, "server": None, "model": None}
        if status is None:
            return info
        if status in (404, 405):
            # No /health (llama-cpp-python, Ollama, LM Studio). The model list is the portable proof that the server is up.
            status, body = self._get("/v1/models")
            if status != 200:
                return info
            body = b"{}"
        try:
            health = json.loads(body or b"{}")
        except ValueError:
            health = {}
        if status == 503:
            info["state"] = "loading"
        elif status == 200:
            info["state"] = "ready"
            if isinstance(health, dict) and health.get("gate") is True and not health.get("loaded"):
                info["state"] = "idle"          # the gate starts the model on the first real request
        else:
            return info
        if info["state"] == "ready":
            code, raw = self._get("/props")
            try:
                props = json.loads(raw) if code == 200 else {}
                n_ctx = ((props.get("default_generation_settings") or {}).get("n_ctx")) if isinstance(props, dict) else None
                info["ctx"] = _int(n_ctx)
                info["server"] = "llama.cpp" if info["ctx"] is not None else None
            except ValueError:
                pass
            code, raw = self._get("/v1/models")
            try:
                data = json.loads(raw) if code == 200 else {}
                first = (data.get("data") or [{}])[0] if isinstance(data, dict) else {}
                info["model"] = str(first.get("id"))[:80] if isinstance(first, dict) and first.get("id") else None
            except (ValueError, TypeError, IndexError):
                pass
        return info

    def wait_ready(self, seconds=60, poll=0.5):
        """Block until the server answers (a model that is still loading answers 503). Returns the probe result."""
        end = time.monotonic() + seconds
        info = self.probe()
        while info["state"] in ("loading", "offline") and time.monotonic() < end:
            time.sleep(poll)
            info = self.probe()
        return info

    # ------------------------------------------------------------------ requests
    def build_request(self, messages, schema=None, max_tokens=512, temperature=0.0, stream=False, schema_mode="json_schema"):
        if not isinstance(messages, list) or not messages:
            raise LLMError("invalid_json", "No messages")
        body = {"model": self.model, "messages": messages, "max_tokens": int(max_tokens), "temperature": temperature, "stream": bool(stream)}
        if self.features["cache_prompt"]:
            body["cache_prompt"] = True
        if self.features["template_kwargs"]:
            body["chat_template_kwargs"] = {"enable_thinking": False}
        if schema is not None:
            if schema_mode == "json_schema":
                body["response_format"] = {"type": "json_schema", "json_schema": {"name": "aiws_action", "strict": True, "schema": schema}}
            elif schema_mode == "json_object_schema":
                body["response_format"] = {"type": "json_object", "schema": schema}
            elif schema_mode == "json_object":
                body["response_format"] = {"type": "json_object"}
        if stream and self.features["stream_options"]:
            body["stream_options"] = {"include_usage": True}
        return body

    def _post(self, body, timeout):
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        if len(raw) > MAX_REQUEST:
            raise LLMError("too_large", "Request is larger than %d KiB" % (MAX_REQUEST // 1024))
        req = urllib.request.Request(self.base + "/v1/chat/completions", data=raw, headers={"Content-Type": "application/json"}, method="POST")
        try:
            return self.opener.open(req, timeout=timeout)
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read(2048).decode("utf-8", "replace")
            except OSError:
                pass
            if exc.code == 503:
                raise LLMError("loading", "The model is still loading")
            raise LLMError("http", "HTTP %d %s" % (exc.code, detail[:160]), detail=detail)
        except TimeoutError:
            raise LLMError("timeout", "The local model did not answer in time")
        except (urllib.error.URLError, OSError) as exc:
            if isinstance(getattr(exc, "reason", None), TimeoutError) or "timed out" in str(exc):
                raise LLMError("timeout", "The local model did not answer in time")
            raise LLMError("unavailable", "The local model is not reachable")

    @staticmethod
    def _read_json(response):
        data = response.read(MAX_RESPONSE + 1)
        if len(data) > MAX_RESPONSE:
            raise LLMError("too_large", "Reply is larger than 1 MiB")
        try:
            doc = json.loads(data)
        except ValueError:
            raise LLMError("invalid_json", "The server did not return JSON")
        if not isinstance(doc, dict):
            raise LLMError("invalid_json", "The server reply has an unexpected shape")
        return doc

    @staticmethod
    def _result(doc, started, first_at=None):
        try:
            choice = doc["choices"][0]
            message = choice.get("message") or {}
            content = message.get("content")
            finish = choice.get("finish_reason")
        except (KeyError, IndexError, TypeError, AttributeError):
            raise LLMError("invalid_json", "The server reply has no choices")
        if not isinstance(content, str):
            content = ""
        end = time.monotonic()
        return {"content": strip_think(content), "finish": finish if isinstance(finish, str) else None, "usage": normalise_usage(doc),
                "timing": {"totalMs": round((end - started) * 1000), "firstTokenMs": None if first_at is None else round((first_at - started) * 1000)}}

    def _stream(self, response, started, on_delta):
        parts, usage_doc, finish, first_at, total = [], {}, None, None, 0
        try:
            while True:
                line = response.readline(65536)
                if not line:
                    break
                total += len(line)
                if total > MAX_RESPONSE:
                    raise LLMError("too_large", "Stream is larger than 1 MiB")
                line = line.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except ValueError:
                    continue
                if not isinstance(chunk, dict):
                    continue
                if isinstance(chunk.get("usage"), dict):
                    usage_doc["usage"] = chunk["usage"]
                if isinstance(chunk.get("timings"), dict):
                    usage_doc["timings"] = chunk["timings"]
                for choice in chunk.get("choices") or []:
                    if not isinstance(choice, dict):
                        continue
                    delta = (choice.get("delta") or {}).get("content")
                    if isinstance(delta, str) and delta:
                        if first_at is None:
                            first_at = time.monotonic()
                        parts.append(delta)
                        if on_delta is not None:
                            try:
                                keep = on_delta(delta)
                            except Exception:                  # a UI callback must never break the run
                                keep = True
                            if keep is False:
                                finish = "cancelled"
                                return {"choices": [{"message": {"content": "".join(parts)}, "finish_reason": finish}], **usage_doc}, first_at
                    if isinstance(choice.get("finish_reason"), str):
                        finish = choice["finish_reason"]
        except (TimeoutError, OSError) as exc:
            raise LLMError("timeout", "The stream stopped: " + str(exc)[:60])
        finally:
            try:
                response.close()
            except OSError:
                pass
        return {"choices": [{"message": {"content": "".join(parts)}, "finish_reason": finish}], **usage_doc}, first_at

    def chat(self, messages, schema=None, max_tokens=512, temperature=0.0, on_delta=None, timeout=None):
        """One model call. Returns {"content", "finish", "usage", "timing", "schemaMode", "degraded"}.
        Optional request fields a server rejects are dropped (and stay dropped) and the call is retried."""
        timeout = self.timeout if timeout is None else timeout
        degraded = []
        mode_i = self.mode_floor if schema is not None else len(SCHEMA_MODES) - 1
        for _ in range(10):
            mode = SCHEMA_MODES[mode_i] if schema is not None else "none"
            stream = on_delta is not None and self.features["stream"]       # the AIWS model gate and the host channel never stream
            body = self.build_request(messages, schema, max_tokens, temperature, stream, mode)
            started = time.monotonic()
            try:
                response = self._post(body, timeout)
            except LLMError as exc:
                if exc.kind != "http":
                    raise
                # Rejected. Drop what the error message points at; if it points at nothing, peel in the order least likely to hurt:
                # streaming extras and the fields only some servers know, then streaming itself, then weaken the structured output
                # one level, structure last of all.
                culprit = blamed_field(exc.detail)
                present = {"stream_options": "stream_options" in body, "chat_template_kwargs": self.features["template_kwargs"] and "chat_template_kwargs" in body,
                           "cache_prompt": self.features["cache_prompt"] and "cache_prompt" in body, "stream": bool(body.get("stream")),
                           "response_format": "response_format" in body and mode_i < len(SCHEMA_MODES) - 1}
                if not present.get(culprit):
                    culprit = next((k for k in ("stream_options", "stream", "cache_prompt", "chat_template_kwargs", "response_format") if present[k]), None)
                if culprit is None:
                    raise
                if culprit == "stream_options":
                    self.features["stream_options"] = False
                    degraded.append("stream_options")
                elif culprit == "stream":
                    self.features["stream"] = False
                    degraded.append("stream")
                elif culprit == "cache_prompt":
                    self.features["cache_prompt"] = False
                    degraded.append("cache_prompt")
                elif culprit == "chat_template_kwargs":
                    self.features["template_kwargs"] = False
                    degraded.append("chat_template_kwargs")
                else:
                    mode_i += 1
                    self.mode_floor = max(self.mode_floor, mode_i)
                    degraded.append("response_format:" + SCHEMA_MODES[mode_i])
                continue
            with response:
                if stream:
                    doc, first_at = self._stream(response, started, on_delta)
                else:
                    doc, first_at = self._read_json(response), None
            result = self._result(doc, started, first_at)
            result["schemaMode"] = mode
            result["degraded"] = degraded
            return result
        raise LLMError("http", "The server rejected the request")

    def complete_json(self, messages, schema, max_tokens=512, repairs=1, on_delta=None, temperature=0.0, normalise=None):
        """Ask for one JSON object that satisfies `schema`. Returns (object, meta). The answer is re-validated here.

        `normalise(obj) -> obj` (optional) is a lenient READER: it fixes near-miss SHAPES before validation (a field under its synonym, a
        harmless extra key). Validation stays strict and never sees anything the normaliser did not make valid; nothing is invented.

        On a validation failure the model gets ONE chance to correct itself with the exact message appended after the
        conversation (so the stable beginning is untouched). `meta["repairMessages"]` holds the two extra messages (the
        rejected answer and the correction request) for the caller to log; they are not added to any history here."""
        meta = {"usage": merge_usage(None, None), "calls": 0, "repairs": 0, "timing": [], "schemaMode": None, "degraded": [], "finish": None}
        work = list(messages)
        last = None
        for attempt in range(repairs + 1):
            result = self.chat(work, schema=schema, max_tokens=max_tokens, temperature=temperature, on_delta=on_delta if attempt == 0 else None)
            meta["calls"] += 1
            meta["usage"] = merge_usage(meta["usage"], result["usage"])
            meta["timing"].append(result["timing"])
            meta["schemaMode"], meta["degraded"], meta["finish"] = result["schemaMode"], result["degraded"], result["finish"]
            if result["finish"] == "cancelled":
                raise LLMError("cancelled", "Cancelled")
            if result["finish"] == "length":
                raise LLMError("truncated", "The answer was cut off by the token limit")
            try:
                obj = parse_json_text(result["content"])
                if normalise is not None:
                    try:
                        obj = normalise(obj)
                    except Exception:                       # a normaliser bug must not turn into a crash: validate the original
                        pass
                aiws_jsonschema.check(obj, schema)
                meta["usage"]["source"] = meta["usage"].get("source", "unknown")
                return obj, meta
            except (LLMError, aiws_jsonschema.SchemaError) as exc:
                last = exc
                if attempt >= repairs:
                    break
                meta["repairs"] += 1
                reason = exc.reason if isinstance(exc, aiws_jsonschema.SchemaError) else str(exc)
                note = [{"role": "assistant", "content": result["content"][:1500]},
                        {"role": "user", "content": "That answer was rejected: %s: %s Reply again with ONLY the corrected JSON object." % (
                            getattr(exc, "path", "$"), reason[:300])}]
                meta["repairMessages"] = note
                work = list(messages) + note
        if isinstance(last, aiws_jsonschema.SchemaError):
            raise LLMError("schema", str(last)[:300])
        raise last
