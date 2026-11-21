"""AIWS same-UID independent, fail-closed policy decision process.

APPLICATION guard only: this is not MAC, UID separation or host isolation.
Every Agent tool path must ask this socket, but code sharing the guest UID
can still bypass it until a future OS-confined worker is introduced.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import socketserver
import sqlite3
import struct
import threading
import time

from aiws_guest_boundary import require_guest_runtime
from aiws_guest_ops import READ_TOOLS as GUEST_READ, TOOLS as GUEST_TOOLS, validate as validate_guest
from aiws_tasks import WRITE_TOOLS, TOOLS as STAGE_TOOLS
from aiws_toolplane import catalog as tool_catalog

DIRECT_READ = frozenset({
    "workspace.tree", "file.read", "file.stat", "code.search", "git.inspect",
    "runtime.detect", "browser.local_text", "platform.inspect",
    "code.symbols", "code.references", "code.dependencies", "code.platformApis"
}) | GUEST_READ
MAX_TASK_WRITES = 8
MAX_RECENT_WRITES = 24
RECENT_SECONDS = 3600

class BrokerDenied(PermissionError):
    pass

def socket_path():
    expected = Path("/run/user") / str(os.getuid())
    if (Path(os.environ.get("XDG_RUNTIME_DIR", "")) != expected
            or expected.is_symlink() or not expected.is_dir()):
        raise BrokerDenied("Dedicated guest runtime directory required")
    return expected / "aiws-broker" / "broker.sock"

def valid_tool(tool, args):
    if (not isinstance(tool, str) or tool not in STAGE_TOOLS
            or not isinstance(args, dict) or len(args) > 16
            or any(not isinstance(k, str) or not isinstance(v, str)
                   or len(v) > 8192 for k, v in args.items())):
        raise BrokerDenied("Unknown tool or invalid bounded arguments")
    if tool in GUEST_TOOLS:
        validate_guest(tool, args)
    else:
        spec = next((t["inputSchema"] for t in tool_catalog()
                     if t["name"] == tool), None)
        if not spec or (set(args) - set(spec["properties"])) or any(
                k not in args for k in spec["required"]):
            raise BrokerDenied("Tool arguments do not match allowlist schema")

class BrokerPolicy:
    def __init__(self, task_db, ledger_db):
        self.task_db = Path(task_db)
        self.ledger_db = Path(ledger_db)
        if not self.ledger_db.is_absolute() or self.ledger_db.is_symlink():
            raise BrokerDenied("Broker ledger must be a private absolute file")
        parent = self.ledger_db.parent
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if parent.is_symlink() or parent.stat().st_mode & 0o077:
            raise BrokerDenied("Broker ledger directory not private")
        self.lock = threading.Lock()
        if self.ledger_db.is_symlink():
            raise BrokerDenied("Broker ledger symlink forbidden")
        with sqlite3.connect(self.ledger_db) as conn:
            conn.execute("PRAGMA synchronous=FULL")
            conn.execute("""CREATE TABLE IF NOT EXISTS granted(
                task_id TEXT NOT NULL, stage_id TEXT NOT NULL,
                run_seq INTEGER NOT NULL, tool TEXT NOT NULL,
                arguments_sha256 TEXT NOT NULL, granted_at INTEGER NOT NULL,
                PRIMARY KEY (task_id, stage_id, run_seq)
            )""")
        os.chmod(self.ledger_db, 0o600)

    def _open_tasks(self):
        if (not self.task_db.is_absolute() or self.task_db.is_symlink()
                or not self.task_db.is_file()):
            raise BrokerDenied("Trusted durable Agent task database unavailable")
        conn = sqlite3.connect(self.task_db.as_uri() + "?mode=ro",
                               uri=True, timeout=2)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        return conn

    def decide(self, req):
        try:
            if not isinstance(req, dict):
                raise BrokerDenied("Invalid Broker request")
            op = req.get("op")
            if op == "authorize_read":
                if set(req) != {"op", "tool", "arguments"}:
                    raise BrokerDenied("Unknown read authorization fields")
                tool, args = req["tool"], req["arguments"]
                if tool not in DIRECT_READ:
                    raise BrokerDenied("Interactive tool is not read-only")
                valid_tool(tool, args)
                return {"allowed": True, "code": "guest-read-only"}
            if op != "authorize_stage" or set(req) != {
                    "op", "taskId", "stageKey", "tool", "arguments"}:
                raise BrokerDenied("Unknown authorization request")
            task_id, key = req["taskId"], req["stageKey"]
            tool, args = req["tool"], req["arguments"]
            if (not isinstance(task_id, str) or not re.fullmatch("[a-f0-9]{32}", task_id)
                    or not isinstance(key, str)
                    or len(key) > 48 or not key.replace("-", "").replace("_", "").isalnum()):
                raise BrokerDenied("Invalid task or stage identifier")
            valid_tool(tool, args)
            with self.lock, self._open_tasks() as tasks:
                row = tasks.execute(
                    "SELECT id, tool, args_json, state, approval FROM stages "
                    "WHERE task_id=? AND stage_key=?", (task_id, key)).fetchone()
                if (row is None or row["state"] != "running" or row["tool"] != tool
                        or json.loads(row["args_json"]) != args):
                    raise BrokerDenied("Not the exact persisted running stage")
                if tool in WRITE_TOOLS:
                    if row["approval"] != 1:
                        raise BrokerDenied("Persisted write approval missing")
                    writes = tuple(sorted(WRITE_TOOLS))
                    placeholders = ",".join("?" for _ in writes)
                    per_task = tasks.execute(
                        "SELECT count(*) FROM stages WHERE task_id=? AND tool IN ("
                        + placeholders + ")", (task_id, *writes)).fetchone()[0]
                    if per_task > MAX_TASK_WRITES:
                        raise BrokerDenied("Per-DAG write budget exceeded")
                    recent = tasks.execute(
                        "SELECT count(*) FROM stages WHERE tool IN ("
                        + placeholders + ") AND state IN ('queued','running','completed')"
                        " AND created_at >= ?", (*writes, int(time.time()) - RECENT_SECONDS)
                    ).fetchone()[0]
                    if recent > MAX_RECENT_WRITES:
                        raise BrokerDenied("Recent global write budget exceeded")
                run = tasks.execute(
                    "SELECT seq FROM audit WHERE task_id=? AND stage_id=?"
                    " AND action='stage.running' ORDER BY seq DESC LIMIT 1",
                    (task_id, row["id"])).fetchone()
                if run is None:
                    raise BrokerDenied("Missing durable stage.running event")
                digest = hashlib.sha256(json.dumps(
                    args, sort_keys=True, ensure_ascii=False,
                    separators=(",", ":")).encode("utf-8")).hexdigest()
                # One authorization per recorded execution attempt. A reviewed
                # interrupted stage has a NEW stage.running audit sequence.
                with sqlite3.connect(self.ledger_db, timeout=3) as ledger:
                    try:
                        ledger.execute(
                            "INSERT INTO granted VALUES(?,?,?,?,?,?)",
                            (task_id, row["id"], run["seq"], tool, digest, int(time.time())))
                    except sqlite3.IntegrityError as exc:
                        raise BrokerDenied("Stage execution receipt already spent") from exc
                return {"allowed": True, "code": "persisted-running-stage"}
        except (BrokerDenied, ValueError, TypeError, KeyError, sqlite3.Error) as exc:
            return {"allowed": False, "code": type(exc).__name__,
                    "reason": str(exc)[:140]}

class BrokerClient:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else socket_path()

    def _authorize(self, req):
        raw = (json.dumps(req, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        if len(raw) > 24576:
            raise BrokerDenied("Broker authorization payload too large")
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
                conn.settimeout(4)
                conn.connect(str(self.path))
                conn.sendall(raw)
                data = b""
                while not data.endswith(b"\n"):
                    chunk = conn.recv(4096)
                    if not chunk:
                        raise BrokerDenied("Broker disconnected")
                    data += chunk
                    if len(data) > 4096:
                        raise BrokerDenied("Broker response oversized")
            response = json.loads(data)
        except (OSError, TimeoutError, UnicodeError, ValueError) as exc:
            raise BrokerDenied("Independent permission Broker unavailable") from exc
        if not isinstance(response, dict) or not response.get("ok"):
            raise BrokerDenied("Invalid permission Broker response")
        decision = response.get("decision", {})
        if not isinstance(decision, dict) or decision.get("allowed") is not True:
            raise BrokerDenied("Broker rejected request: " + str(
                decision.get("reason", "not authorized"))[:140])
        return decision

    def authorize_stage(self, task_id, key, tool, args):
        return self._authorize({"op": "authorize_stage", "taskId": task_id,
                                "stageKey": key, "tool": tool, "arguments": args})

    def authorize_read(self, tool, args):
        return self._authorize({"op": "authorize_read",
                                "tool": tool, "arguments": args})

class _Handler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            if not hasattr(socket, "SO_PEERCRED"):
                raise BrokerDenied("Linux peer credentials required")
            _pid, uid, _gid = struct.unpack(
                "3i", self.request.getsockopt(
                    socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid != os.getuid():
                raise BrokerDenied("Broker peer UID mismatch")
            packet = self.rfile.readline(24577)
            if not packet or len(packet) > 24576 or not packet.endswith(b"\n"):
                raise BrokerDenied("Malformed or oversized Broker IPC")
            request = json.loads(packet)
            decision = self.server.policy.decide(request)
            fingerprint = hashlib.sha256(packet).hexdigest()[:16]
            # No raw arguments, source files, prompts, names or paths in log.
            print(json.dumps({"broker": "same-uid-policy",
                              "requestHash16": fingerprint,
                              "allowed": decision["allowed"],
                              "code": decision["code"]}), flush=True)
            response = {"ok": True, "decision": decision}
        except (BrokerDenied, ValueError, TypeError, UnicodeError) as exc:
            response = {"ok": False, "error": type(exc).__name__}
        self.wfile.write((json.dumps(response, ensure_ascii=False) + "\n").encode())

class BrokerServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    allow_reuse_address = False

def serve(policy, path):
    path = Path(path)
    if (not path.parent.is_dir() or path.parent.is_symlink()
            or path.parent.stat().st_mode & 0o077
            or path.exists() or path.is_symlink()):
        raise BrokerDenied("Broker socket must be new and in a private directory")
    server = BrokerServer(str(path), _Handler)
    server.policy = policy
    os.chmod(path, 0o600)
    return server

def main():
    require_guest_runtime()
    if os.geteuid() == 0:
        raise BrokerDenied("Permission Broker must not run as root")
    home = Path.home().resolve(strict=True)
    state = Path(os.environ.get("XDG_STATE_HOME", str(home / ".local/state")))
    if not state.is_absolute() or state.is_symlink() or not state.resolve().is_relative_to(home):
        raise BrokerDenied("Broker state must remain in dedicated guest home")
    folder = state / "aiws"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    endpoint = socket_path()
    endpoint.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    policy = BrokerPolicy(folder / "tasks.sqlite3", folder / "broker-decisions.sqlite3")
    server = serve(policy, endpoint)
    try:
        print("AIWS_BROKER_READY same_uid_only=yes", flush=True)
        server.serve_forever(poll_interval=.2)
    finally:
        server.server_close()
        endpoint.unlink(missing_ok=True)

if __name__ == "__main__":
    main()
