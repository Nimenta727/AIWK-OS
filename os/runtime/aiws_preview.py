"""Project preview: a tiny, read-only static file server for ONE folder of the workspace, on 127.0.0.1 only.

It lets the user look at what was built (a web page, generated docs, a bundler's output) in the workbench's preview tab.
Hardening (each point is tested):
  * GET/HEAD only; no directory listing (a folder serves its index.html or 404);
  * nothing outside the folder: '..', encoded dots, backslashes, NUL, absolute-looking paths and symlinks anywhere on the way are refused;
  * hidden files and folders (names starting with '.') are never served (so .git, .env and .aiws-* stay private);
  * the Host header must be this server's own loopback address (defeats DNS rebinding);
  * responses are never cached, never sniffed, send no referrer; HTML gets a CSP that only allows the page's own origin;
  * it stops by itself after a quiet period, and only one preview runs at a time.
"""
import mimetypes
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

MAX_FILE = 50 << 20
IDLE_SECONDS = 900
MIME = {".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css", ".html": "text/html", ".htm": "text/html", ".json": "application/json",
        ".svg": "image/svg+xml", ".wasm": "application/wasm", ".map": "application/json", ".txt": "text/plain", ".md": "text/plain", ".xml": "application/xml",
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp", ".ico": "image/x-icon",
        ".woff": "font/woff", ".woff2": "font/woff2", ".ttf": "font/ttf", ".mp3": "audio/mpeg", ".mp4": "video/mp4", ".webm": "video/webm"}
# frame-ancestors: the workbench embeds the preview from another loopback port. Everything else may only come from the page's own origin.
CSP = ("default-src 'self' data: blob:; script-src 'self' 'unsafe-inline' 'unsafe-eval' blob:; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
       "connect-src 'self'; font-src 'self' data:; media-src 'self' blob:; object-src 'none'; base-uri 'self'; form-action 'self'; "
       "frame-ancestors http://127.0.0.1:* http://localhost:*")


class PreviewError(Exception):
    """Safe-to-show rejection."""


def resolve(root, url_path):
    """Map a URL path to a file under root, or None. Pure and strict; this is the security-critical function."""
    if "\x00" in url_path or "\\" in url_path:
        return None
    raw = unquote(url_path)
    if "\x00" in raw or "\\" in raw or "%" in raw:                  # a second layer of encoding is never legitimate here
        return None
    parts = [p for p in raw.split("/") if p not in ("", ".")]
    if any(p == ".." or p.startswith(".") for p in parts):
        return None
    cur = Path(root)
    for p in parts:
        cur = cur / p
        if cur.is_symlink():
            return None
    if cur.is_dir():
        cur = cur / "index.html"
        if cur.is_symlink():
            return None
    try:
        if not cur.is_file() or not cur.resolve().is_relative_to(Path(root).resolve()):
            return None
    except OSError:
        return None
    return cur


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    server_version = "AIWSPreview"
    sys_version = ""

    def log_message(self, *a):
        pass

    def _host_ok(self):
        host = self.headers.get("Host", "")
        port = self.server.server_address[1]
        return host in ("127.0.0.1:%d" % port, "localhost:%d" % port)

    def _send(self, status, body=b"", ctype="text/plain; charset=utf-8", head=False, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def _serve(self, head):
        self.server.owner.touch()
        if not self._host_ok():
            return self._send(403, b"forbidden", head=head)
        target = resolve(self.server.root, urlsplit(self.path).path)
        if target is None:
            return self._send(404, b"not found", head=head)
        try:
            size = target.stat().st_size
            if size > MAX_FILE:
                return self._send(413, b"file too large", head=head)
            data = b"" if head else target.read_bytes()
        except OSError:
            return self._send(404, b"not found", head=head)
        ext = target.suffix.lower()
        mime = MIME.get(ext) or mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if mime.startswith("text/") or mime in ("application/json", "application/xml", "image/svg+xml"):
            mime += "; charset=utf-8"
        extra = {"Content-Security-Policy": CSP} if ext in (".html", ".htm", ".svg") else {}
        if head:                                                   # HEAD reports the real length without reading the file
            self.send_response(200)
            for k, v in (("Content-Type", mime), ("Content-Length", str(size)), ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"), *extra.items()):
                self.send_header(k, v)
            return self.end_headers()
        self._send(200, data, mime, extra=extra)

    def do_GET(self):
        self._serve(False)

    def do_HEAD(self):
        self._serve(True)

    def _no(self):
        self._send(405, b"method not allowed", extra={"Allow": "GET, HEAD"})
    do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _no


class Preview:
    """One running preview. `clock` is injectable for the idle test."""
    def __init__(self, directory, idle_seconds=IDLE_SECONDS, clock=time.monotonic):
        self.root = str(Path(directory).resolve())
        self.idle, self.clock, self.last = idle_seconds, clock, clock()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.server.daemon_threads = True
        self.server.root, self.server.owner = self.root, self
        self.port = self.server.server_address[1]
        self.url = "http://127.0.0.1:%d/" % self.port
        self.stopped = threading.Event()
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True, name="aiws-preview").start()
        threading.Thread(target=self._watch, daemon=True, name="aiws-preview-idle").start()

    def touch(self):
        self.last = self.clock()

    def _watch(self):
        while not self.stopped.wait(0.5):
            if self.clock() - self.last > self.idle:
                self.stop()

    def stop(self):
        if self.stopped.is_set():
            return
        self.stopped.set()
        self.server.shutdown()
        self.server.server_close()


class PreviewManager:
    """Owned by the workbench. At most one preview; starting another replaces it."""
    def __init__(self, workspace, resolve_dir):
        self.workspace, self.resolve_dir, self.current, self.rel, self.lock = workspace, resolve_dir, None, None, threading.Lock()

    def start(self, rel):
        path = self.resolve_dir(self.workspace, rel)             # same confinement as every other path in the platform
        if not path.is_dir():
            raise PreviewError("The preview target must be a folder")
        with self.lock:
            if self.current:
                self.current.stop()
            self.current, self.rel = Preview(path), rel
            return self.status()

    def stop(self):
        with self.lock:
            if self.current:
                self.current.stop()
            self.current = None
            return self.status()

    def status(self):
        cur = self.current
        if cur is not None and cur.stopped.is_set():
            self.current = cur = None
        return {"running": cur is not None, "url": cur.url if cur else None, "path": self.rel if cur else None}
