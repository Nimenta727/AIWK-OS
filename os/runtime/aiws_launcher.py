"""Desktop launcher: starts a registered GUI program for an APPROVED `app.launch` stage.

Why a separate socket: the Agent (which runs approved stages) is sandboxed with a private /tmp and no network, so it
cannot reach the X11 display. The workbench runs in the user's graphical session. The Agent therefore asks the workbench
to do the one thing only it can - and the workbench does NOT trust the request: it re-checks, read-only, that the exact
stage is persisted, RUNNING, approved by the user, and carries exactly {"id": <registered gui app>}. A completed, pending,
unapproved or altered stage is refused, so a process that merely finds this socket cannot start anything by asking.

Same-UID application-level guard, like the Broker: it limits mistakes and confused deputies, it is not OS isolation.
"""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import socket
import socketserver
import sqlite3
import struct
import threading

import aiws_apps

TOOL = "app.launch"
MAX_REQUEST = 1024

class LauncherDenied(PermissionError):
    pass

def socket_path():
    expected = Path("/run/user") / str(os.getuid())
    if (Path(os.environ.get("XDG_RUNTIME_DIR", "")) != expected or expected.is_symlink() or not expected.is_dir()):
        raise LauncherDenied("Dedicated guest runtime directory required")
    return expected / "aiws-launcher" / "launcher.sock"

class LauncherPolicy:
    def __init__(self, task_db, workspace, launch=None):
        self.task_db = Path(task_db)
        self.workspace = workspace
        self.launch = launch or aiws_apps.launch
        self.spent = set()
        self.lock = threading.Lock()

    def _open(self):
        if self.task_db.is_symlink() or not self.task_db.is_file():
            raise LauncherDenied("Trusted task database unavailable")
        conn = sqlite3.connect(self.task_db.as_uri() + "?mode=ro", uri=True, timeout=2)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        return conn

    def decide(self, request):
        try:
            if not isinstance(request, dict) or set(request) != {"taskId", "stageKey", "id"}:
                raise LauncherDenied("Expected taskId, stageKey and id")
            task_id, key, app_id = request["taskId"], request["stageKey"], request["id"]
            if (not all(isinstance(v, str) for v in (task_id, key, app_id)) or len(task_id) != 32
                    or len(key) > 48 or app_id not in aiws_apps.IDS):
                raise LauncherDenied("Invalid identifiers")
            with self.lock, closing(self._open()) as conn:
                row = conn.execute("SELECT id, tool, args_json, state, approval FROM stages WHERE task_id=? AND stage_key=?",
                                   (task_id, key)).fetchone()
                if row is None or row["tool"] != TOOL or row["state"] != "running":
                    raise LauncherDenied("Not the exact persisted running launch stage")
                if row["approval"] != 1:
                    raise LauncherDenied("The user has not approved this launch")
                if json.loads(row["args_json"]) != {"id": app_id}:
                    raise LauncherDenied("Stage arguments differ from the request")
                run = conn.execute("SELECT seq FROM audit WHERE task_id=? AND stage_id=? AND action='stage.running' "
                                   "ORDER BY seq DESC LIMIT 1", (task_id, row["id"])).fetchone()
                if run is None:
                    raise LauncherDenied("Missing durable stage.running event")
                receipt = (task_id, row["id"], run["seq"])
                if receipt in self.spent:
                    raise LauncherDenied("This execution has already launched")
                self.spent.add(receipt)
            return {"allowed": True, "result": self.launch(app_id, self.workspace)}
        except (LauncherDenied, ValueError, TypeError, KeyError, sqlite3.Error, FileNotFoundError) as exc:
            return {"allowed": False, "code": type(exc).__name__, "reason": str(exc)[:140]}

class _Handler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            if not hasattr(socket, "SO_PEERCRED"):
                raise LauncherDenied("Linux peer credentials required")
            _pid, uid, _gid = struct.unpack("3i", self.request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid != os.getuid():
                raise LauncherDenied("Peer UID mismatch")
            self.request.settimeout(4)
            packet = self.rfile.readline(MAX_REQUEST + 1)
            if not packet or len(packet) > MAX_REQUEST or not packet.endswith(b"\n"):
                raise LauncherDenied("Malformed or oversized request")
            decision = self.server.policy.decide(json.loads(packet))
            print(json.dumps({"launcher": "approved-stage-only", "requestHash16": hashlib.sha256(packet).hexdigest()[:16],
                              "allowed": decision["allowed"]}), flush=True)          # no names, paths or arguments in the log
            response = {"ok": True, "decision": decision}
        except (LauncherDenied, ValueError, TypeError, UnicodeError, OSError) as exc:
            response = {"ok": False, "error": type(exc).__name__}
        try:
            self.wfile.write((json.dumps(response, ensure_ascii=False) + "\n").encode())
        except OSError:
            pass

class LauncherServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    allow_reuse_address = False

def serve(policy, path):
    path = Path(path)
    if (not path.parent.is_dir() or path.parent.is_symlink() or path.parent.stat().st_mode & 0o077
            or path.exists() or path.is_symlink()):
        raise LauncherDenied("Launcher socket must be new and in a private directory")
    server = LauncherServer(str(path), _Handler)
    server.policy = policy
    os.chmod(path, 0o600)
    return server

def start_in_thread(policy, path=None):
    """Create the private directory + socket and serve in a daemon thread. Returns the server (call .shutdown())."""
    path = Path(path) if path is not None else socket_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_socket():
        path.unlink()                                        # stale socket from a previous workbench process
    server = serve(policy, path)
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True, name="aiws-launcher").start()
    return server

class LauncherClient:
    def __init__(self, path=None):
        self._path = Path(path) if path is not None else None       # resolved lazily: only graphical-session guests need it

    @property
    def path(self):
        return self._path if self._path is not None else socket_path()

    def launch(self, task_id, key, app_id):
        raw = (json.dumps({"taskId": task_id, "stageKey": key, "id": app_id}, separators=(",", ":")) + "\n").encode()
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
                conn.settimeout(6)
                conn.connect(str(self.path))
                conn.sendall(raw)
                data = b""
                while not data.endswith(b"\n"):
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                    if len(data) > 8192:
                        raise LauncherDenied("Launcher response oversized")
            response = json.loads(data)
        except (OSError, ValueError) as exc:
            raise LauncherDenied("The desktop launcher is not available (is the graphical workbench running?)") from exc
        decision = response.get("decision") if isinstance(response, dict) else None
        if not isinstance(decision, dict) or decision.get("allowed") is not True:
            raise LauncherDenied("Launch refused: " + str((decision or {}).get("reason", "not authorized"))[:140])
        return decision["result"]
