"""Lazy-start / idle-unload gate in front of llama-server (step O5). Standard library only.

Why: the model weights are the biggest resident memory cost of the whole system. This small process listens on the
public loopback model port, starts llama-server on an internal loopback port ONLY when a real request arrives, and
stops it again after an idle period, so an unused model costs (almost) no RAM.

It also narrows the attack surface of the inference server:
  * only GET /health, GET /gate/status and POST /v1/chat/completions are served (no /props, /slots, /metrics, ...);
  * request bodies are validated (size, JSON, allowed keys, no streaming, bounded max_tokens/messages);
  * one request at a time (llama-server runs with --parallel 1 anyway), bounded queue wait;
  * the child command must be llama-server bound to 127.0.0.1 on the internal port.
`/health` is answered by the gate itself and NEVER loads the model, so status polling costs nothing.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "127.0.0.1"
MAX_BODY = 64 * 1024
MAX_RESPONSE = 1024 * 1024
ALLOWED_KEYS = {"model", "messages", "stream", "temperature", "max_tokens", "response_format", "cache_prompt"}
MODEL_ALIAS = "aiws-local"
MAX_MESSAGES, MAX_CONTENT, MAX_TOKENS = 8, 16000, 1024
CRASH_WINDOW, CRASH_LIMIT, COOLDOWN = 60.0, 3, 30.0

class GateError(ValueError):
    pass

def validate_child_argv(argv, child_port, allowed_names=("llama-server",)):
    if not isinstance(argv, list) or not argv or any(not isinstance(a, str) for a in argv):
        raise GateError("The child command must be a list of strings")
    if Path(argv[0]).name not in allowed_names:
        raise GateError("Only llama-server may be started by the gate")
    def value(flag):
        return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else None
    if value("--host") != HOST or value("--port") != str(child_port):
        raise GateError("llama-server must bind %s:%s" % (HOST, child_port))
    return argv

def read_rss_mib(pid):
    out = {"rssMiB": None, "peakRssMiB": None}
    try:
        for line in Path("/proc/%d/status" % pid).read_text().splitlines():
            if line.startswith("VmRSS:"):
                out["rssMiB"] = round(int(line.split()[1]) / 1024, 1)
            elif line.startswith("VmHWM:"):
                out["peakRssMiB"] = round(int(line.split()[1]) / 1024, 1)
    except (OSError, ValueError, IndexError):
        pass
    return out

class ModelGate:
    def __init__(self, child_argv, listen_port=18080, child_port=18081, idle_seconds=300.0, start_timeout=180.0,
                 request_timeout=180.0, queue_timeout=60.0, allowed_names=("llama-server",), popen=subprocess.Popen, clock=time.monotonic):
        self.argv = validate_child_argv(child_argv, child_port, allowed_names)
        # idle_seconds == 0 means RESIDENT: the model is loaded at start-up, never unloaded for being idle, and is restarted
        # if it dies. Right for a dedicated GPU (nothing else needs that memory); the idle unload is for shared CPU RAM.
        if idle_seconds != 0 and not 0.2 <= idle_seconds <= 86400:
            raise GateError("idle_seconds must be 0 (resident) or between 0.2 and 86400")
        self.resident = idle_seconds == 0
        self.child_port, self.idle_seconds = child_port, idle_seconds
        self.start_timeout, self.request_timeout, self.queue_timeout = start_timeout, request_timeout, queue_timeout
        self.popen, self.clock = popen, clock
        self.child = None
        self.lock = threading.RLock()          # short critical sections only: child handle and counters
        self.start_lock = threading.Lock()     # serialises cold starts (held while waiting for readiness)
        self.serial = threading.Lock()         # one inference request at a time
        self.inflight = 0
        self.last_activity = clock()
        self.stats = {"requests": 0, "rejected": 0, "coldStarts": 0, "idleUnloads": 0, "crashes": 0, "lastColdStartSeconds": None}
        self.crash_times = []
        self.cooldown_until = 0.0
        self.stop = threading.Event()
        self.server = ThreadingHTTPServer((HOST, listen_port), _Handler)
        self.server.daemon_threads = True
        self.server.gate = self
        self.port = self.server.server_address[1]
        self.monitor = threading.Thread(target=self._monitor, daemon=True, name="aiws-model-idle")

    # ---- lifecycle -------------------------------------------------------------------
    def loaded(self):
        with self.lock:
            return self.child is not None and self.child.poll() is None

    def _child_healthy(self):
        try:
            with urllib.request.urlopen("http://%s:%d/health" % (HOST, self.child_port), timeout=1.0) as r:
                return r.status == 200
        except (OSError, urllib.error.URLError):
            return False

    def _note_crash(self):
        now = self.clock()
        self.stats["crashes"] += 1
        self.crash_times = [t for t in self.crash_times if now - t < CRASH_WINDOW] + [now]
        if len(self.crash_times) >= CRASH_LIMIT:
            self.cooldown_until = now + COOLDOWN

    def ensure_loaded(self):
        """Start the child if needed and wait until it is ready. Raises GateError('<status>:<message>').

        Only one request starts the model; waiting happens OUTSIDE the state lock so /health and /gate/status
        stay instantly responsive while a cold start is in progress.
        """
        with self.start_lock:
            with self.lock:
                if self.loaded():
                    return
                if self.clock() < self.cooldown_until:
                    raise GateError("503:The model keeps failing to start; retry later")
                if self.child is not None:                       # it died on its own since the last request
                    self._note_crash()
                    self.child = None
                    if self.clock() < self.cooldown_until:
                        raise GateError("503:The model keeps failing to start; retry later")
                started = self.clock()
                try:
                    child = self.popen(self.argv, stdin=subprocess.DEVNULL, shell=False, close_fds=True)
                except OSError as exc:
                    raise GateError("503:Cannot start the model (%s)" % type(exc).__name__) from exc
                self.child = child
            deadline = started + self.start_timeout
            while True:
                if child.poll() is not None:
                    with self.lock:
                        self._note_crash()
                        if self.child is child:
                            self.child = None
                    raise GateError("503:The model exited while starting")
                if self._child_healthy():
                    break
                if self.clock() > deadline:
                    with self.lock:
                        if self.child is child:
                            self._stop_child()
                    raise GateError("504:The model did not become ready in time")
                time.sleep(0.05)
            with self.lock:
                self.stats["coldStarts"] += 1
                self.stats["lastColdStartSeconds"] = round(self.clock() - started, 3)

    def _stop_child(self):
        child, self.child = self.child, None
        if child is None:
            return
        try:
            child.terminate()
            child.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            try:
                child.kill()
                child.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass

    def _keep_resident(self):
        """Resident mode: (re)start the model whenever it is not running. A failing model is retried only after the
        crash cooldown that ensure_loaded() already enforces, so a broken model cannot spin the CPU."""
        with self.lock:
            needs = not self.loaded() and self.clock() >= self.cooldown_until and self.inflight == 0
        if needs:
            try:
                self.ensure_loaded()
                self.stats["residentRestarts"] = self.stats.get("residentRestarts", 0) + (1 if self.stats["coldStarts"] > 1 else 0)
            except GateError:
                pass

    def _monitor(self):
        tick = 0
        while not self.stop.wait(0.2):
            tick += 1
            if self.resident:
                if tick % 5 == 1:                       # about once a second
                    self._keep_resident()
                continue
            with self.lock:
                if (self.child is not None and self.child.poll() is None and self.inflight == 0
                        and self.clock() - self.last_activity > self.idle_seconds):
                    self._stop_child()                         # unload: weights leave RAM
                    self.stats["idleUnloads"] += 1

    # ---- request path ----------------------------------------------------------------
    def forward(self, body):
        """Run one validated chat request through the child. Returns (status, bytes)."""
        if not self.serial.acquire(timeout=self.queue_timeout):
            raise GateError("503:The model is busy")
        try:
            with self.lock:
                self.inflight += 1
            try:
                self.ensure_loaded()
                request = urllib.request.Request("http://%s:%d/v1/chat/completions" % (HOST, self.child_port), data=body,
                                                 headers={"Content-Type": "application/json"}, method="POST")
                try:
                    with urllib.request.urlopen(request, timeout=self.request_timeout) as response:
                        data = response.read(MAX_RESPONSE + 1)
                        status = response.status
                except urllib.error.HTTPError as exc:
                    data, status = exc.read(MAX_RESPONSE + 1), exc.code
                except (OSError, urllib.error.URLError) as exc:
                    raise GateError("502:The model did not answer (%s)" % type(exc).__name__) from exc
                if len(data) > MAX_RESPONSE:
                    raise GateError("502:The model response is too large")
                with self.lock:
                    self.stats["requests"] += 1
                return status, data
            finally:
                with self.lock:
                    self.inflight -= 1
                    self.last_activity = self.clock()
        finally:
            self.serial.release()

    def status(self):
        with self.lock:
            pid = self.child.pid if self.loaded() else None
            data = {"gate": True, "loaded": pid is not None, "childPid": pid, "idleSeconds": self.idle_seconds, "resident": self.resident,
                    "secondsSinceLastRequest": round(self.clock() - self.last_activity, 1), "inflight": self.inflight, **self.stats}
        data.update(read_rss_mib(pid) if pid else {"rssMiB": None, "peakRssMiB": None})
        return data

    def start(self):
        self.monitor.start()
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True, name="aiws-model-gate").start()

    def serve_forever(self):
        self.monitor.start()
        self.server.serve_forever(poll_interval=0.2)

    def close(self):
        self.stop.set()
        self.server.shutdown()
        self.server.server_close()
        with self.lock:
            self._stop_child()

def validate_request(raw):
    """Return the validated JSON body or raise GateError('<status>:<message>')."""
    try:
        data = json.loads(raw)
    except ValueError:
        raise GateError("400:Body must be JSON")
    if not isinstance(data, dict) or set(data) - ALLOWED_KEYS:
        raise GateError("400:Unsupported request fields")
    if data.get("stream") not in (None, False):
        raise GateError("400:Streaming is not supported")
    if data.get("model", MODEL_ALIAS) != MODEL_ALIAS:
        raise GateError("400:Unknown model alias")
    messages = data.get("messages")
    if (not isinstance(messages, list) or not 1 <= len(messages) <= MAX_MESSAGES
            or any(not isinstance(m, dict) or set(m) != {"role", "content"} or m["role"] not in ("system", "user")
                   or not isinstance(m["content"], str) or len(m["content"]) > MAX_CONTENT for m in messages)):
        raise GateError("400:Invalid messages")
    tokens = data.get("max_tokens", 256)
    if isinstance(tokens, bool) or not isinstance(tokens, int) or not 1 <= tokens <= MAX_TOKENS:
        raise GateError("400:max_tokens must be 1-%d" % MAX_TOKENS)
    temperature = data.get("temperature", 0)
    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)) or not 0 <= temperature <= 2:
        raise GateError("400:Invalid temperature")
    if "cache_prompt" in data and not isinstance(data["cache_prompt"], bool):
        raise GateError("400:Invalid cache_prompt")
    if "response_format" in data:
        rf = data["response_format"]
        if not isinstance(rf, dict) or rf.get("type") not in ("json_object", "json_schema") or len(json.dumps(rf)) > 20000:
            raise GateError("400:Invalid response_format")
    return data

class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *args):
        return

    def _send(self, status, payload, raw=False):
        body = payload if raw else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, text):
        status, _, message = text.partition(":")
        self.server.gate.stats["rejected"] += 1
        self._send(int(status) if status.isdigit() else 500, {"error": message})

    def do_GET(self):
        gate = self.server.gate
        if self.path == "/health":
            return self._send(200, {"status": "ok", "gate": True, "loaded": gate.loaded()})      # never loads the model
        if self.path == "/gate/status":
            return self._send(200, gate.status())
        self._error("404:Not found")

    def do_POST(self):
        gate = self.server.gate
        if self.path != "/v1/chat/completions":
            return self._error("404:Not found")
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            return self._error("415:JSON required")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self._error("400:Invalid length")
        if length <= 0 or length > MAX_BODY:
            return self._error("413:Request too large or empty")
        raw = self.rfile.read(length)
        try:
            validate_request(raw)
            status, data = gate.forward(raw)
        except GateError as exc:
            return self._error(str(exc) if ":" in str(exc) and str(exc)[:3].isdigit() else "400:" + str(exc))
        self._send(status, data, raw=True)

def main():
    parser = argparse.ArgumentParser(description="AIWS lazy-start model gate")
    parser.add_argument("--listen-port", type=int, default=18080)
    parser.add_argument("--child-port", type=int, default=18081)
    parser.add_argument("--idle-seconds", type=float, default=300.0)
    parser.add_argument("--resident", action="store_true", help="keep the model loaded and restart it if it dies")
    parser.add_argument("child", nargs=argparse.REMAINDER, help="-- llama-server ...")
    args = parser.parse_args()
    child = args.child[1:] if args.child and args.child[0] == "--" else args.child
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        parser.error("The model gate must not run as root")
    try:
        gate = ModelGate(child, listen_port=args.listen_port, child_port=args.child_port, idle_seconds=0 if args.resident else args.idle_seconds)
    except GateError as exc:
        parser.error(str(exc))
    signal.signal(signal.SIGTERM, lambda *a: (gate.close(), sys.exit(0)))
    try:
        gate.serve_forever()
    finally:
        gate.close()

if __name__ == "__main__":
    main()
