"""AIWS OS guest-local read-only workbench service and tool task controller.

An unprivileged single-user prototype; not an autonomous model or privileged broker.
"""
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import threading
import time
from urllib.parse import urlsplit
from uuid import uuid4
from aiws_toolplane import audit, catalog, invoke
from aiws_guest_boundary import require_guest_runtime, protect_guest_workspace

HOST = "127.0.0.1"
PORT = 17640
READ_ONLY = frozenset({"workspace.tree", "file.read", "code.search", "git.inspect",
                       "runtime.detect", "browser.local_text", "platform.inspect",
                       "code.symbols", "code.references", "code.dependencies", "code.platformApis"})
ASSETS = {".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml",
          ".png": "image/png", ".jpg": "image/jpeg", ".ico": "image/x-icon",
          ".woff2": "font/woff2"}

class Controller:
    def __init__(self, workspace, ui):
        self.workspace = Path(workspace)
        self.ui = Path(ui)
        self.csrf = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.records = {}
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="aiws-agent")

    def health(self):
        return {"system": "AIWS OS", "mode": "linux-guest",
                "agent": "local-tool-controller", "llmConnected": False,
                "agentPrivileged": False, "guestOnly": True,
                "workspace": str(self.workspace),
                "desktopInstalled": bool(shutil.which("xfce4-session")),
                "displayManagerInstalled": bool(shutil.which("lightdm")),
                "uiBundled": (self.ui / "index.html").is_file(),
                "toolCount": len(READ_ONLY),
                "note": "No autonomous LLM inference, privileged broker or host VM access."}

    def recent(self):
        with self.lock:
            return [dict(x) for x in list(self.records.values())[-24:]][::-1]

    def job(self, identifier):
        with self.lock:
            item = self.records.get(identifier)
            return dict(item) if item else None

    def submit(self, tool, args):
        spec = next((x["inputSchema"] for x in catalog() if x["name"] == tool), None)
        if tool not in READ_ONLY or spec is None:
            raise ValueError("Tool is not exposed to the workbench")
        if not isinstance(args, dict) or any(k not in spec["properties"] for k in args):
            raise ValueError("Unknown tool arguments")
        if any(k not in args for k in spec["required"]):
            raise ValueError("Missing required tool arguments")
        if any(not isinstance(v, str) for v in args.values()):
            raise ValueError("Tool arguments must be strings")
        item = {"id": uuid4().hex, "tool": tool, "status": "queued",
                "result": None, "error": None, "submittedAt": int(time.time())}
        with self.lock:
            if sum(x["status"] in ("queued", "running") for x in self.records.values()) >= 8:
                raise ValueError("Agent queue full")
            self.records[item["id"]] = item
            if len(self.records) > 64:
                for old in list(self.records):
                    if len(self.records) <= 64:
                        break
                    if self.records[old]["status"] not in ("queued", "running"):
                        del self.records[old]
        self.pool.submit(self._execute, item["id"], tool, args)
        return dict(item)

    def _execute(self, identifier, tool, args):
        with self.lock:
            self.records[identifier]["status"] = "running"
        try:
            result = invoke(tool, args)
            encoded = json.dumps(result, ensure_ascii=False)
            if len(encoded) > 65536:
                result = {"preview": encoded[:32000], "truncated": True}
            status, error = "completed", None
            audit(tool, args, True)
        except Exception as exc:
            result, status, error = None, "failed", type(exc).__name__ + ": " + str(exc)[:240]
            audit(tool, args, False)
        with self.lock:
            self.records[identifier].update(
                status=status, error=error, result=result, finishedAt=int(time.time()))

class Handler(BaseHTTPRequestHandler):
    server_version = "AIWS-Guest/0.2"

    def log_message(self, format, *args):
        pass

    def reply(self, status, data, media="application/json; charset=utf-8"):
        if not isinstance(data, bytes):
            data = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", media)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                         "img-src 'self' data:; font-src 'self' data:; connect-src 'self'; "
                         "frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(data)

    def check_host(self):
        return self.headers.get("Host") == HOST + ":" + str(self.server.server_port)

    def do_GET(self):
        if not self.check_host():
            return self.reply(403, {"error": "Invalid host"})
        app = self.server.application
        path = urlsplit(self.path).path
        if path == "/api/v1/health":
            return self.reply(200, app.health())
        if path == "/api/v1/session":
            return self.reply(200, {"csrf": app.csrf, "mode": "linux-guest"})
        if path == "/api/v1/snapshot":
            return self.reply(200, {"health": app.health(), "jobs": app.recent(),
                                    "capabilities": [x for x in catalog() if x["name"] in READ_ONLY]})
        if path.startswith("/api/v1/jobs/"):
            job = app.job(path.removeprefix("/api/v1/jobs/"))
            return self.reply(200, job) if job else self.reply(404, {"error": "Unknown job"})
        if path == "/os-bridge.js":
            return self.reply(200, b"window.__AIWS_OS_WORKBENCH__ = true;\n", "text/javascript")
        if path == "/":
            try:
                source = (app.ui / "index.html").read_text(encoding="utf-8")
                if "</head>" not in source:
                    raise ValueError("Missing head")
            except (OSError, ValueError):
                return self.reply(503, {"error": "React workbench assets missing"})
            source = source.replace("</head>", '<script src="/os-bridge.js"></script></head>', 1)
            return self.reply(200, source.encode("utf-8"), "text/html; charset=utf-8")
        if not path.startswith("/assets/"):
            return self.reply(404, {"error": "Not found"})
        target = app.ui / path.lstrip("/")
        try:
            ui_assets = (app.ui / "assets").resolve(strict=True)
            file = target.resolve(strict=True)
            if not file.is_relative_to(ui_assets) or not file.is_file():
                raise OSError("Outside assets")
            if target.is_symlink() or file.suffix not in ASSETS or file.stat().st_size > 8 * 1024 * 1024:
                raise OSError("Invalid asset")
            return self.reply(200, file.read_bytes(), ASSETS[file.suffix])
        except OSError:
            return self.reply(404, {"error": "Missing asset"})

    def do_POST(self):
        if not self.check_host():
            return self.reply(403, {"error": "Invalid host"})
        if urlsplit(self.path).path != "/api/v1/jobs":
            return self.reply(404, {"error": "Not found"})
        origin = self.headers.get("Origin")
        expected = "http://" + HOST + ":" + str(self.server.server_port)
        if origin is not None and origin != expected:
            return self.reply(403, {"error": "Invalid origin"})
        if self.headers.get("X-AIWS-CSRF") != self.server.application.csrf:
            return self.reply(403, {"error": "Invalid CSRF"})
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            return self.reply(415, {"error": "JSON required"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self.reply(400, {"error": "Invalid length"})
        if not 0 < length <= 16384:
            return self.reply(413, {"error": "Request too large or empty"})
        try:
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict) or set(payload) != {"tool", "arguments"}:
                raise ValueError("Expected tool and arguments")
            result = self.server.application.submit(payload["tool"], payload["arguments"])
        except (ValueError, KeyError, TypeError) as exc:
            return self.reply(400, {"error": str(exc)[:240]})
        return self.reply(202, result)

def make_server(workspace, ui, port=PORT):
    root = Path(workspace).resolve(strict=True)
    if not root.is_dir() or root in (Path("/"), Path.home()):
        raise ValueError("Dedicated workspace required")
    server = ThreadingHTTPServer((HOST, port), Handler)
    server.daemon_threads = True
    server.application = Controller(root, ui)
    return server

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    try:
        require_guest_runtime()
    except PermissionError as exc:
        parser.error(str(exc))
    workspace = Path(os.environ.get("AIWS_WORKSPACE", str(Path.home() / ".local/share/aiws/projects"))).expanduser()
    if not workspace.is_absolute() or workspace.is_symlink() or workspace in (Path("/"), Path.home()):
        parser.error("Workspace must be a dedicated non-symlink absolute folder")
    workspace.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        protect_guest_workspace(workspace.resolve(strict=True))
    except PermissionError as exc:
        parser.error(str(exc))
    os.environ["AIWS_WORKSPACE"] = str(workspace.resolve(strict=True))
    ui = Path(os.environ.get("AIWS_UI_DIR", "/usr/local/share/aiws/workbench"))
    if args.self_check:
        print(json.dumps({"workspace": str(workspace), "uiBundled": (ui / "index.html").is_file(),
                          "toolCount": len(READ_ONLY)}))
        return
    server = make_server(workspace, ui, args.port)
    print("AIWS guest workbench http://" + HOST + ":" + str(server.server_port), flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()
        server.application.pool.shutdown(wait=True, cancel_futures=True)

if __name__ == "__main__":
    main()
