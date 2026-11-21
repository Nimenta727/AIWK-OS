"""Tolerant adapters: official CLI JSONL output -> aiws.event.v1. Pure parsing.

No process is started and no socket is opened here: the supervisor (a later step) owns the child
process and feeds lines in. Parsers never raise on provider data; anything they do not understand
becomes an explicit "unrecognized" event, and missing usage becomes source="unknown" (never a guess).
Message text is never copied into events; only lengths, tool names and a short redacted summary.

IMPORTANT: field names below follow the vendors' public documentation and common observed output, but
they were NOT verified against a real CLI run in this repository. Real recorded fixtures are step O6.
"""
import json
from pathlib import Path
import time

from aiws_events import (UNRECOGNIZED, EventError, make_event, redact, safe_name)

MAX_LINE = 1024 * 1024
MAX_FILE = 8 * 1024 * 1024
MAX_LINES = 100000

def _int(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 10 ** 12 else None

def _describe(name, data):
    """A very short hint of what a tool call does, with secrets removed."""
    if not isinstance(data, dict):
        return None
    for key in ("command", "file_path", "path", "pattern", "url", "query"):
        if isinstance(data.get(key), str) and data[key].strip():
            return redact(data[key], 120)
    return None

class _Base:
    agent = "claude"

    def __init__(self, session, clock=time.time):
        self.session = safe_name(session, "session")
        self.clock = clock
        self.lines = 0
        self.invalid = 0
        self.ended = False
        self.failed = False
        self.turns = 0          # assistant turns seen, for the supervisor's turn limit

    def _ev(self, kind, **fields):
        try:
            return [make_event(self.clock(), self.agent, self.session, kind, **fields)]
        except EventError:
            return [make_event(self.clock(), self.agent, self.session, "error", detail="event rejected by schema")]

    def _unrecognized(self, src):
        return self._ev("message", src=redact(src, 48) or "unknown", detail=UNRECOGNIZED)

    def _bad_line(self, why):
        self.invalid += 1
        # a runaway garbage stream must not flood the store: first 5, then every 100th
        if self.invalid <= 5 or self.invalid % 100 == 0:
            return self._ev("error", detail=why, src="invalid-line")
        return []

    def feed(self, line):
        self.lines += 1
        if isinstance(line, bytes):
            line = line.decode("utf-8", errors="replace")
        if len(line) > MAX_LINE:
            return self._bad_line("oversized line skipped")
        if not line.strip():
            return []
        try:
            data = json.loads(line)
        except ValueError:
            return self._bad_line("unparseable line")
        if not isinstance(data, dict):
            return self._bad_line("line is not a JSON object")
        try:
            return self.handle(data)
        except Exception:      # a provider format surprise must never crash the observer
            return self._ev("error", detail="adapter could not interpret an event", src="adapter-error")

    def handle(self, data):
        raise NotImplementedError

    def finish(self):
        """Call when the stream closed. A stream that never reported an end is recorded as unknown."""
        if self.ended:
            return []
        self.ended = True
        return self._ev("end", status="unknown", detail="stream closed without a result")

class ClaudeStreamAdapter(_Base):
    """`claude -p --output-format stream-json --verbose` (field names unverified, see module doc)."""
    agent = "claude"

    def __init__(self, session, clock=time.time):
        super().__init__(session, clock)
        self.tool_names = {}
        self.usage_seen = {}
        self.counted = set()

    def _usage_delta(self, message_id, usage):
        fields = {"in": "input_tokens", "out": "output_tokens",
                  "cacheRead": "cache_read_input_tokens", "cacheWrite": "cache_creation_input_tokens"}
        current = {k: _int(usage.get(v)) for k, v in fields.items()}
        previous = self.usage_seen.get(message_id, {})
        delta = {}
        for key, value in current.items():
            if value is None:
                continue
            step = value - (previous.get(key) or 0)      # the same message may repeat its usage per block
            if step > 0:
                delta[key] = step
            previous[key] = max(value, previous.get(key) or 0)
        self.usage_seen[message_id] = previous
        return current, delta

    def handle(self, data):
        kind = data.get("type")
        if kind == "system":
            if data.get("subtype") == "init":
                model = data.get("model")
                return self._ev("start", detail=redact(model, 60) if isinstance(model, str) else "claude session")
            return []
        if kind == "stream_event":
            return []
        if kind == "assistant":
            return self._assistant(data.get("message"))
        if kind == "user":
            return self._tool_results(data.get("message"))
        if kind == "result":
            return self._result(data)
        return self._unrecognized(str(kind))

    def _assistant(self, message):
        if not isinstance(message, dict):
            return self._unrecognized("assistant")
        out, text_chars = [], 0
        blocks = message.get("content") if isinstance(message.get("content"), list) else []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                name = safe_name(block.get("name"), "tool")
                if isinstance(block.get("id"), str):
                    self.tool_names[block["id"][:80]] = name
                hint = _describe(name, block.get("input"))
                out += self._ev("tool", tool=name, status="pending", **({"detail": hint} if hint else {}))
            elif block.get("type") == "text" and isinstance(block.get("text"), str):
                text_chars += len(block["text"])
        if text_chars:
            out += self._ev("message", detail="%d chars" % text_chars)
        message_id = message.get("id") if isinstance(message.get("id"), str) else "m%d" % self.lines
        if message_id not in self.usage_seen and message_id not in self.counted:
            self.turns += 1
        self.counted.add(message_id[:80])
        usage = message.get("usage")
        if isinstance(usage, dict):
            current, delta = self._usage_delta(message_id[:80], usage)
            if delta:
                out += self._ev("usage", tokens={**{k: delta.get(k) for k in ("in", "out", "cacheRead", "cacheWrite")},
                                                  "source": "reported", "scope": "delta"})
            elif not any(v is not None for v in current.values()):
                out += self._ev("usage", tokens={"source": "unknown", "scope": "delta"})
        elif message_id not in self.usage_seen:
            self.usage_seen[message_id] = {}
            out += self._ev("usage", tokens={"source": "unknown", "scope": "delta"})
        return out

    def _tool_results(self, message):
        out = []
        blocks = message.get("content") if isinstance(message, dict) and isinstance(message.get("content"), list) else []
        for block in blocks:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                name = self.tool_names.get(str(block.get("tool_use_id"))[:80], "unknown")
                out += self._ev("tool", tool=name, status="error" if block.get("is_error") is True else "ok")
        return out

    def _result(self, data):
        out = []
        usage = data.get("usage")
        if isinstance(usage, dict):
            total = {"in": _int(usage.get("input_tokens")), "out": _int(usage.get("output_tokens")),
                     "cacheRead": _int(usage.get("cache_read_input_tokens")),
                     "cacheWrite": _int(usage.get("cache_creation_input_tokens"))}
            if any(v is not None for v in total.values()):
                out += self._ev("usage", tokens={**total, "source": "reported", "scope": "total"})
            else:
                out += self._ev("usage", tokens={"source": "unknown", "scope": "total"})
        else:
            out += self._ev("usage", tokens={"source": "unknown", "scope": "total"})
        subtype = data.get("subtype") if isinstance(data.get("subtype"), str) else "unknown"
        ok = subtype == "success" and data.get("is_error") is not True
        fields = {"status": "ok" if ok else "error", "detail": redact(subtype, 48)}
        cost = data.get("total_cost_usd")
        if isinstance(cost, (int, float)) and not isinstance(cost, bool) and 0 <= cost <= 1e6:
            fields["cost"] = {"usd": float(cost), "source": "reported"}
        self.ended = True
        self.failed = not ok
        return out + self._ev("end", **fields)

class CodexJsonAdapter(_Base):
    """`codex exec --json` (event names per vendor docs; unverified against a real run)."""
    agent = "codex"
    TOOL_ITEMS = {"command_execution": "command", "file_change": "file_change", "web_search": "web_search",
                  "mcp_tool_call": "mcp", "collab_tool_call": "agent_call"}

    def __init__(self, session, clock=time.time):
        super().__init__(session, clock)
        self.open_items = {}
        self.completed_turn = False

    @staticmethod
    def _normalise(data):
        if "type" not in data and isinstance(data.get("method"), str):      # alternative method/params style
            params = data.get("params") if isinstance(data.get("params"), dict) else {}
            return data["method"].replace("/", "."), params
        return data.get("type"), data

    def _tool_name(self, item):
        kind = item.get("type")
        base = self.TOOL_ITEMS.get(kind)
        if kind == "mcp_tool_call" and isinstance(item.get("tool"), str):
            return safe_name("mcp_" + item["tool"], "mcp")
        return base

    def handle(self, data):
        kind, body = self._normalise(data)
        if kind == "thread.started":
            return self._ev("start", detail="codex thread")
        if kind == "turn.started":
            self.turns += 1
            return []
        if kind is None:
            return self._unrecognized("none")
        if kind in ("item.started", "item.updated"):
            item = body.get("item") if isinstance(body.get("item"), dict) else {}
            name = self._tool_name(item)
            if name and kind == "item.started":
                ident = str(item.get("id", ""))[:80]
                self.open_items[ident] = name
                hint = _describe(name, {"command": item.get("command")} if item.get("command") else item)
                return self._ev("tool", tool=name, status="pending", **({"detail": hint} if hint else {}))
            return []
        if kind == "item.completed":
            return self._item_completed(body.get("item") if isinstance(body.get("item"), dict) else {})
        if kind == "turn.completed":
            self.completed_turn = True
            usage = body.get("usage")
            if isinstance(usage, dict):
                counts = {"in": _int(usage.get("input_tokens")), "out": _int(usage.get("output_tokens")),
                          "cacheRead": _int(usage.get("cached_input_tokens")), "cacheWrite": None}
                if any(v is not None for v in counts.values()):
                    return self._ev("usage", tokens={**counts, "source": "reported", "scope": "turn"})
            return self._ev("usage", tokens={"source": "unknown", "scope": "turn"})
        if kind == "turn.failed":
            self.ended, self.failed = True, True
            err = body.get("error") if isinstance(body.get("error"), dict) else {}
            return (self._ev("error", detail=redact(err.get("message", "turn failed"), 120), src="turn.failed") +
                    self._ev("end", status="error", detail="turn failed"))
        if kind == "error":
            self.failed = True
            return self._ev("error", detail=redact(body.get("message", "error"), 120), src="error")
        return self._unrecognized(str(kind))

    def _item_completed(self, item):
        kind = item.get("type")
        name = self._tool_name(item)
        if name:
            ident = str(item.get("id", ""))[:80]
            out = []
            if ident not in self.open_items:      # some builds only emit the completed event
                out += self._ev("tool", tool=name, status="pending")
            self.open_items.pop(ident, None)
            if kind == "command_execution":
                code = item.get("exit_code")
                status = "unknown" if not isinstance(code, int) or isinstance(code, bool) else ("ok" if code == 0 else "error")
            else:
                status = "error" if item.get("status") == "failed" else "ok"
            return out + self._ev("tool", tool=name, status=status)
        if kind == "agent_message" and isinstance(item.get("text"), str):
            return self._ev("message", detail="%d chars" % len(item["text"]))
        if kind in ("reasoning",):
            return []
        if kind == "error":
            return self._ev("error", detail=redact(item.get("message", "item error"), 120), src="item.error")
        return self._unrecognized("item:" + str(kind))

    def finish(self):
        if self.ended:
            return []
        self.ended = True
        if self.completed_turn and not self.failed:
            return self._ev("end", status="ok", detail="turn completed")
        return self._ev("end", status="error" if self.failed else "unknown", detail="stream closed")

def replay(path, adapter, store):
    """Feed a recorded JSONL file through an adapter into a store (bounded; used by tests and O3)."""
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_FILE:
        raise EventError("Replay file must be a regular file up to 8 MiB")
    events = errors = 0
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for number, line in enumerate(stream, 1):
            if number > MAX_LINES:
                break
            for event in adapter.feed(line):
                store.append(event)
                events += 1
                errors += event["kind"] == "error"
    for event in adapter.finish():
        store.append(event)
        events += 1
    return {"lines": adapter.lines, "events": events, "errors": errors}
