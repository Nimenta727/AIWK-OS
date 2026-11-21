#!/usr/bin/env python3
"""Host-GPU model channel: the guest never gets a network path to the model, only one virtio-serial pipe.

  guest  (mode "guest")  listens on 127.0.0.1:18080 (what the workbench already talks to) and forwards each request as one
                         frame over the serial device /dev/virtio-ports/aiws.model.
  host   (mode "host")   reads frames from the QEMU chardev (unix socket, or a Windows named pipe), checks them again, and
                         calls the host's own llama-server on 127.0.0.1 only. The host opens NO listening port for the guest.

Frame = 4-byte big-endian length + UTF-8 JSON. Request {id, method, path, body}; response {id, status, body}.
Only an allowlist of paths; no streaming; one request in flight; size and time limits on both sides. Content is never
logged, only sizes and status, so the audit log cannot leak prompts. Standard library only (runs on Linux and Windows hosts).
"""
import argparse
import json
import os
import struct
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

ALLOWED = {("GET", "/health"), ("GET", "/v1/models"), ("POST", "/v1/chat/completions"), ("POST", "/v1/completions")}
MAX_REQUEST = 1 << 20          # 1 MiB prompt
MAX_RESPONSE = 4 << 20
TIMEOUT = 300


class ChannelError(Exception):
    pass


def write_frame(stream, obj, limit):
    data = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    if len(data) > limit:
        raise ChannelError("frame too large")
    stream.write(struct.pack(">I", len(data)) + data)
    stream.flush()


def _read_exact(stream, n, deadline):
    buf = b""
    while len(buf) < n:
        if time.monotonic() > deadline:
            raise ChannelError("timeout")
        chunk = stream.read(n - len(buf))
        if not chunk:
            raise ChannelError("channel closed")
        buf += chunk
    return buf


def read_frame(stream, limit, timeout=TIMEOUT):
    deadline = time.monotonic() + timeout
    (n,) = struct.unpack(">I", _read_exact(stream, 4, deadline))
    if n > limit:
        raise ChannelError("frame too large")           # the stream is now desynchronised; callers must close it
    try:
        obj = json.loads(_read_exact(stream, n, deadline).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise ChannelError("bad frame")
    if not isinstance(obj, dict):
        raise ChannelError("bad frame")
    return obj


# ---------------- guest side ----------------
class GuestBridge:
    def __init__(self, stream, log=None):
        self.stream, self.lock, self.log, self.seq = stream, threading.Lock(), log or (lambda *_: None), 0

    def call(self, method, path, body):
        if (method, path) not in ALLOWED:
            return 404, b'{"error":"not available over the model channel"}'
        if len(body) > MAX_REQUEST:
            return 413, b'{"error":"request too large"}'
        if not self.lock.acquire(timeout=5):                # one in flight: the host GPU model is single-slot
            return 503, b'{"error":"model busy"}'
        try:
            self.seq += 1
            rid = self.seq
            started = time.monotonic()
            try:
                write_frame(self.stream, {"id": rid, "method": method, "path": path, "body": body.decode("utf-8", "replace")}, MAX_REQUEST + 4096)
                reply = read_frame(self.stream, MAX_RESPONSE)
            except (ChannelError, OSError) as exc:
                self.log("channel-error", len(body), 0, str(exc))
                return 502, b'{"error":"model channel unavailable"}'
            if reply.get("id") != rid:
                return 502, b'{"error":"model channel out of sync"}'
            out = str(reply.get("body", "")).encode("utf-8")
            self.log(path, len(body), len(out), int(reply.get("status", 502)), round(time.monotonic() - started, 2))
            return int(reply.get("status", 502)), out
        finally:
            self.lock.release()


def make_guest_server(bridge, port):
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"
        def log_message(self, *a):
            pass
        def _go(self, method):
            try:
                n = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                n = -1
            if n < 0 or n > MAX_REQUEST:
                status, body = 413, b'{"error":"request too large"}'
            else:
                status, body = bridge.call(method, self.path.split("?", 1)[0], self.rfile.read(n) if n else b"")
            self.send_response(status); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        def do_GET(self):
            self._go("GET")
        def do_POST(self):
            self._go("POST")
    return ThreadingHTTPServer(("127.0.0.1", port), H)          # loopback only


# ---------------- host side ----------------
def serve_host(stream, upstream, log=None, stop=lambda: False):
    """Answer frames until the channel closes. `upstream` must be a loopback URL on the HOST."""
    log = log or (lambda *_: None)
    while not stop():
        try:
            req = read_frame(stream, MAX_REQUEST + 4096, timeout=10 ** 9)
        except ChannelError as exc:
            log("channel-closed", str(exc)); return
        rid, method, path = req.get("id"), req.get("method"), req.get("path")
        body = str(req.get("body", "")).encode("utf-8")
        if (method, path) not in ALLOWED or len(body) > MAX_REQUEST:
            status, out = 404, '{"error":"not allowed"}'
        else:
            try:
                r = urlrequest.Request(upstream + path, data=body if method == "POST" else None, method=method,
                                       headers={"Content-Type": "application/json"})
                with urlrequest.urlopen(r, timeout=TIMEOUT) as resp:
                    status, out = resp.status, resp.read(MAX_RESPONSE + 1).decode("utf-8", "replace")
            except HTTPError as exc:
                status, out = exc.code, exc.read(MAX_RESPONSE + 1).decode("utf-8", "replace")
            except (URLError, OSError, TimeoutError):
                status, out = 502, '{"error":"host model unavailable"}'
            if len(out.encode("utf-8")) > MAX_RESPONSE:
                status, out = 502, '{"error":"response too large"}'
        log(path, len(body), len(out), status)
        try:
            write_frame(stream, {"id": rid, "status": status, "body": out}, MAX_RESPONSE + 4096)
        except (ChannelError, OSError):
            return


def _upstream_ok(url):
    from urllib.parse import urlsplit
    u = urlsplit(url)
    return u.scheme == "http" and u.hostname in ("127.0.0.1", "localhost", "::1") and not u.path.strip("/")


def _open_host_stream(target):
    if sys.platform == "win32" and target.startswith("\\\\.\\pipe\\"):
        return open(target, "r+b", buffering=0)
    import socket
    s = socket.socket(socket.AF_UNIX); s.connect(target)
    f = s.makefile("rwb", buffering=0)
    return f


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("mode", choices=("guest", "host"))
    ap.add_argument("--device", default="/dev/virtio-ports/aiws.model", help="guest: serial device")
    ap.add_argument("--port", type=int, default=18080, help="guest: loopback port")
    ap.add_argument("--chardev", help="host: unix socket path or \\\\.\\pipe\\name of the QEMU chardev")
    ap.add_argument("--upstream", default="http://127.0.0.1:8080", help="host: llama-server (loopback only)")
    a = ap.parse_args()
    log = lambda *x: print(time.strftime("%H:%M:%S"), *x, flush=True)
    if a.mode == "guest":
        if os.geteuid() == 0:
            sys.exit("must not run as root")
        stream = open(a.device, "r+b", buffering=0)
        make_guest_server(GuestBridge(stream, log), a.port).serve_forever()
    else:
        if not a.chardev or not _upstream_ok(a.upstream):
            sys.exit("host mode needs --chardev and a loopback --upstream URL without a path")
        serve_host(_open_host_stream(a.chardev), a.upstream.rstrip("/"), log)


if __name__ == "__main__":
    main()
