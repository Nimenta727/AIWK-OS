"""AIWS observatory event schema (aiws.event.v1) and a small bounded event store.

Pure standard library. No sockets, no processes, no model calls.

Principles
  * Events describe WHAT happened (kind, tool name, status, token counts), never message text.
  * Token numbers are only ever copied from what a provider REPORTED. If it did not report them the
    event says source="unknown" and every count is None. Nothing is estimated or invented.
  * Everything is bounded: field sizes, events per session, sessions kept.
  * This is an observability log, not a tamper-proof audit chain (the task DAG audit is that).
"""
import json
from pathlib import Path
import re
import sqlite3
import threading

EVENT_VERSION = 1
EVENT_KINDS = ("start", "message", "tool", "usage", "approval", "error", "end")
STATUSES = ("ok", "error", "denied", "pending", "unknown")
AGENTS = ("claude", "codex", "deepseek", "local", "router", "supervisor")
TOKEN_FIELDS = ("in", "out", "cacheRead", "cacheWrite")
CTX_KINDS = ("file", "url", "search", "command", "prompt")
SCOPES = ("delta", "total", "turn")      # turn: reported per turn, cumulative-vs-increment NOT verified
UNRECOGNIZED = "unrecognized"            # detail marker for provider events we do not understand
MAX_EVENTS_PER_SESSION = 20000
MAX_TOKEN = 10 ** 12
SAFE_NAME = re.compile(r"^[A-Za-z0-9_.:\-]{1,64}\Z")
SECRET = re.compile(r"(?i)\b([A-Za-z0-9_]*(?:token|secret|password|passwd|api[_-]?key|authorization))\b\s*[=:]\s*(?:bearer\s+)?\S+")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{8,}")

class EventError(ValueError):
    pass

def safe_name(value, fallback="unknown"):
    text = re.sub(r"[^A-Za-z0-9_.:\-]", "_", str(value or ""))[:64]
    return text if text else fallback

def redact(text, limit=120):
    """One short single-line summary with obvious secrets removed. Never full content."""
    text = CONTROL.sub(" ", str(text))
    text = BEARER.sub("Bearer [redacted]", text)           # first: a bare "Bearer <token>" anywhere
    text = SECRET.sub(lambda m: m.group(1) + "=[redacted]", text)
    return text.strip()[:limit]

def _token_count(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_TOKEN:
        raise EventError("Invalid token count")
    return value

def validate_event(event):
    """Strict validation; returns a normalised copy. Unknown keys are rejected."""
    allowed = {"v", "ts", "agent", "session", "kind", "tool", "status", "tokens", "cost", "detail", "src",
               "node", "parent", "model", "label", "ctx", "prog"}
    if not isinstance(event, dict) or set(event) - allowed:
        raise EventError("Unknown event fields")
    if event.get("v") != EVENT_VERSION:
        raise EventError("Unsupported event version")
    ts = event.get("ts")
    if isinstance(ts, bool) or not isinstance(ts, (int, float)) or not 0 < ts < 4102444800:
        raise EventError("Invalid timestamp")
    if event.get("agent") not in AGENTS or event.get("kind") not in EVENT_KINDS:
        raise EventError("Invalid agent or kind")
    if not isinstance(event.get("session"), str) or not SAFE_NAME.match(event["session"]):
        raise EventError("Invalid session id")
    out = {"v": 1, "ts": float(ts), "agent": event["agent"], "session": event["session"], "kind": event["kind"]}
    if "tool" in event:
        if not isinstance(event["tool"], str) or not SAFE_NAME.match(event["tool"]):
            raise EventError("Invalid tool name")
        out["tool"] = event["tool"]
    if "status" in event:
        if event["status"] not in STATUSES:
            raise EventError("Invalid status")
        out["status"] = event["status"]
    if "tokens" in event:
        t = event["tokens"]
        if not isinstance(t, dict) or set(t) - (set(TOKEN_FIELDS) | {"source", "scope"}):
            raise EventError("Invalid tokens object")
        if t.get("source") not in ("reported", "unknown") or t.get("scope", "delta") not in SCOPES:
            raise EventError("Invalid token source or scope")
        counts = {k: _token_count(t.get(k)) for k in TOKEN_FIELDS}
        if t["source"] == "unknown" and any(v is not None for v in counts.values()):
            raise EventError("Unknown-source usage must not carry numbers")
        if t["source"] == "reported" and all(v is None for v in counts.values()):
            raise EventError("Reported usage needs at least one number")
        out["tokens"] = {**counts, "source": t["source"], "scope": t.get("scope", "delta")}
    if "cost" in event:
        c = event["cost"]
        if (not isinstance(c, dict) or set(c) != {"usd", "source"} or c["source"] != "reported"
                or isinstance(c["usd"], bool) or not isinstance(c["usd"], (int, float)) or not 0 <= c["usd"] <= 1e6):
            raise EventError("Invalid cost")
        out["cost"] = {"usd": float(c["usd"]), "source": "reported"}
    if "detail" in event:
        if not isinstance(event["detail"], str) or len(event["detail"]) > 200 or CONTROL.search(event["detail"]):
            raise EventError("Invalid detail")
        out["detail"] = event["detail"]
    if "src" in event:
        if not isinstance(event["src"], str) or len(event["src"]) > 48 or CONTROL.search(event["src"]):
            raise EventError("Invalid src")
        out["src"] = event["src"]
    for key in ("node", "parent"):                       # sub-agent tree: ids are provider call ids, never free text
        if key in event:
            if not isinstance(event[key], str) or not SAFE_NAME.match(event[key]):
                raise EventError("Invalid " + key)
            out[key] = event[key]
    for key, limit in (("model", 60), ("label", 100)):
        if key in event:
            if not isinstance(event[key], str) or len(event[key]) > limit or CONTROL.search(event[key]):
                raise EventError("Invalid " + key)
            out[key] = event[key]
    if "ctx" in event:                                    # context the node was given/used: short typed references
        c = event["ctx"]
        if (not isinstance(c, list) or len(c) > 8 or any(
                not isinstance(x, dict) or set(x) != {"kind", "ref"} or x["kind"] not in CTX_KINDS
                or not isinstance(x["ref"], str) or not 1 <= len(x["ref"]) <= 120 or CONTROL.search(x["ref"]) for x in c)):
            raise EventError("Invalid ctx")
        out["ctx"] = [{"kind": x["kind"], "ref": x["ref"]} for x in c]
    if "prog" in event:
        g = event["prog"]
        if (not isinstance(g, dict) or set(g) != {"tools", "ms"} or any(
                isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 10 ** 9 for v in g.values())):
            raise EventError("Invalid prog")
        out["prog"] = {"tools": g["tools"], "ms": g["ms"]}
    return out

def make_event(ts, agent, session, kind, **fields):
    return validate_event({"v": EVENT_VERSION, "ts": ts, "agent": agent, "session": session, "kind": kind, **fields})

class EventStore:
    def __init__(self, folder):
        self.folder = Path(folder)
        if not self.folder.is_absolute() or self.folder.is_symlink():
            raise EventError("Event store must be an absolute, non-symlink directory")
        self.folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.folder.is_symlink() or self.folder.stat().st_mode & 0o077:
            raise EventError("Event store directory must be mode 0700")
        path = self.folder / "events.sqlite3"
        if path.is_symlink():
            raise EventError("Event database symlinks are forbidden")
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, timeout=10, isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS sessions(
            session TEXT PRIMARY KEY, agent TEXT NOT NULL, started REAL NOT NULL, ended REAL, status TEXT,
            events INTEGER NOT NULL DEFAULT 0, tool_calls INTEGER NOT NULL DEFAULT 0,
            tool_errors INTEGER NOT NULL DEFAULT 0, errors INTEGER NOT NULL DEFAULT 0,
            unrecognized INTEGER NOT NULL DEFAULT 0, unknown_usage INTEGER NOT NULL DEFAULT 0,
            d_in INTEGER, d_out INTEGER, d_cr INTEGER, d_cw INTEGER,
            t_in INTEGER, t_out INTEGER, t_cr INTEGER, t_cw INTEGER,
            turn_semantics_unverified INTEGER NOT NULL DEFAULT 0,
            cost_usd REAL, truncated INTEGER NOT NULL DEFAULT 0)""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS events(
            seq INTEGER PRIMARY KEY AUTOINCREMENT, session TEXT NOT NULL, ts REAL NOT NULL,
            kind TEXT NOT NULL, body TEXT NOT NULL)""")
        self.db.execute("CREATE INDEX IF NOT EXISTS events_session ON events(session, seq)")

    def close(self):
        with self.lock:
            self.db.close()

    def append(self, event):
        e = validate_event(event)
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                row = self.db.execute("SELECT events FROM sessions WHERE session=?", (e["session"],)).fetchone()
                if row is None:
                    self.db.execute("INSERT INTO sessions(session,agent,started) VALUES(?,?,?)",
                                    (e["session"], e["agent"], e["ts"]))
                    count = 0
                else:
                    count = row["events"]
                    self.db.execute("UPDATE sessions SET started=MIN(started,?) WHERE session=?", (e["ts"], e["session"]))
                self._apply(e)
                if count < MAX_EVENTS_PER_SESSION:
                    self.db.execute("INSERT INTO events(session,ts,kind,body) VALUES(?,?,?,?)",
                                    (e["session"], e["ts"], e["kind"], json.dumps(e, sort_keys=True, separators=(",", ":"))))
                else:
                    self.db.execute("UPDATE sessions SET truncated=1 WHERE session=?", (e["session"],))
                self.db.execute("UPDATE sessions SET events=events+1 WHERE session=?", (e["session"],))
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise
        return e

    def _apply(self, e):
        s, kind, status = e["session"], e["kind"], e.get("status")
        if e.get("detail") == UNRECOGNIZED:
            self.db.execute("UPDATE sessions SET unrecognized=unrecognized+1 WHERE session=?", (s,))
        if kind == "end":
            self.db.execute("UPDATE sessions SET ended=?, status=? WHERE session=?", (e["ts"], status or "unknown", s))
        elif kind == "error":
            self.db.execute("UPDATE sessions SET errors=errors+1 WHERE session=?", (s,))
        elif kind == "tool":
            if status == "pending":
                self.db.execute("UPDATE sessions SET tool_calls=tool_calls+1 WHERE session=?", (s,))
            elif status in ("error", "denied"):
                self.db.execute("UPDATE sessions SET tool_errors=tool_errors+1 WHERE session=?", (s,))
        if "cost" in e:
            self.db.execute("UPDATE sessions SET cost_usd=? WHERE session=?", (e["cost"]["usd"], s))
        t = e.get("tokens")
        if t is None:
            return
        if t["source"] == "unknown":
            self.db.execute("UPDATE sessions SET unknown_usage=unknown_usage+1 WHERE session=?", (s,))
        elif t["scope"] == "total":      # cumulative figure from the provider: keep the latest
            self.db.execute("UPDATE sessions SET t_in=?,t_out=?,t_cr=?,t_cw=? WHERE session=?",
                            (t["in"], t["out"], t["cacheRead"], t["cacheWrite"], s))
        else:
            if t["scope"] == "turn":
                self.db.execute("UPDATE sessions SET turn_semantics_unverified=1 WHERE session=?", (s,))
            # a field never reported stays NULL (shown as unknown), it is not turned into 0
            for column, key in (("d_in", "in"), ("d_out", "out"), ("d_cr", "cacheRead"), ("d_cw", "cacheWrite")):
                if t[key] is not None:
                    self.db.execute("UPDATE sessions SET %s=COALESCE(%s,0)+? WHERE session=?" % (column, column),
                                    (t[key], s))

    @staticmethod
    def _summary(row):
        has_total = row["t_in"] is not None or row["t_out"] is not None or row["t_cr"] is not None or row["t_cw"] is not None
        has_delta = any(row[k] is not None for k in ("d_in", "d_out", "d_cr", "d_cw"))
        if has_total:
            basis = "reported-total"
            tokens = {"in": row["t_in"], "out": row["t_out"], "cacheRead": row["t_cr"], "cacheWrite": row["t_cw"]}
        elif has_delta:
            basis = "sum-of-reported"
            tokens = {"in": row["d_in"], "out": row["d_out"], "cacheRead": row["d_cr"], "cacheWrite": row["d_cw"]}
        else:
            basis = "none"
            tokens = {"in": None, "out": None, "cacheRead": None, "cacheWrite": None}
        return {"session": row["session"], "agent": row["agent"], "started": row["started"], "ended": row["ended"],
                "status": row["status"] or ("running" if row["ended"] is None else "unknown"),
                "events": row["events"], "toolCalls": row["tool_calls"], "toolErrors": row["tool_errors"],
                "errors": row["errors"], "unrecognizedEvents": row["unrecognized"],
                "tokens": {**tokens, "basis": basis, "unknownUsageEvents": row["unknown_usage"],
                           # a "turn" figure may be cumulative or per-turn: the sum is then only indicative
                           "verified": not (basis == "sum-of-reported" and row["turn_semantics_unverified"])},
                "costUsd": row["cost_usd"], "truncated": bool(row["truncated"])}

    def summary(self, session):
        with self.lock:
            row = self.db.execute("SELECT * FROM sessions WHERE session=?", (session,)).fetchone()
        if row is None:
            raise EventError("Unknown session")
        return self._summary(row)

    def sessions(self, limit=50):
        limit = max(1, min(int(limit), 200))
        with self.lock:
            rows = self.db.execute("SELECT * FROM sessions ORDER BY started DESC LIMIT ?", (limit,)).fetchall()
        return [self._summary(r) for r in rows]

    def events(self, session, after=0, limit=200):
        limit = max(1, min(int(limit), 500))
        with self.lock:
            rows = self.db.execute("SELECT seq, body FROM events WHERE session=? AND seq>? ORDER BY seq LIMIT ?",
                                   (session, int(after), limit)).fetchall()
        return [{"seq": r["seq"], **json.loads(r["body"])} for r in rows]

    def recent(self, limit=12):
        limit = max(1, min(int(limit), 50))
        with self.lock:
            rows = self.db.execute("SELECT seq, body FROM events ORDER BY seq DESC LIMIT ?", (limit,)).fetchall()
        return [{"seq": r["seq"], **json.loads(r["body"])} for r in rows]

    def prune(self, max_sessions=200):
        """Keep only the newest sessions: bounded disk use."""
        with self.lock:
            old = [r["session"] for r in self.db.execute(
                "SELECT session FROM sessions ORDER BY started DESC LIMIT -1 OFFSET ?", (int(max_sessions),)).fetchall()]
            for s in old:
                self.db.execute("DELETE FROM events WHERE session=?", (s,))
                self.db.execute("DELETE FROM sessions WHERE session=?", (s,))
        return len(old)
