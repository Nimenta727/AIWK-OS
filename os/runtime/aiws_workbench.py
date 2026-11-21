"""AIWS OS guest-local workbench with persistent guest task/DAG control.

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
from aiws_tasks import GuestTaskStore, TaskError
from aiws_guest_ops import GuestOperations, TOOLS as GUEST_OP_TOOLS, catalog as guest_catalog
from aiws_model_registry import GuestModelRegistry
from aiws_agent_client import AgentClient, TaskProxy, ReadOnlySystemProxy, ReadOnlyToolProxy, AgentUnavailable, AgentError
from aiws_local_model import LocalPlanner, LocalModelError
import subprocess

HOST = "127.0.0.1"
PORT = 17640
READ_ONLY = frozenset({"workspace.tree", "file.read", "code.search", "git.inspect",
                       "runtime.detect", "browser.local_text", "platform.inspect",
                       "code.symbols", "code.references", "code.dependencies", "code.platformApis"})
GUEST_WRITES = frozenset({"file.replace"})
# No direct guest write through transient /jobs: use approved durable DAG.
EXPOSED = READ_ONLY
ASSETS = {".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml",
          ".png": "image/png", ".jpg": "image/jpeg", ".ico": "image/x-icon",
          ".woff2": "font/woff2"}

class Controller:
    def __init__(self, workspace, ui, singleton=False):
        self.workspace = Path(workspace)
        self.ui = Path(ui)
        self.csrf = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.records = {}
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="aiws-agent")
        state_home = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))).expanduser()
        if singleton:
            # The production guest state DB must never live on a host/shared
            # mount, even if XDG_STATE_HOME has been overridden.
            home = Path.home().resolve(strict=True)
            if not state_home.is_absolute() or state_home.is_symlink() or not (
                    state_home.resolve(strict=False).is_relative_to(home)):
                raise PermissionError("AIWS state directory must live inside the guest user's home")
            state_home.mkdir(parents=True, exist_ok=True, mode=0o700)
            protect_guest_workspace(state_home.resolve(strict=True))
        self.agent = AgentClient() if singleton else None
        self.file_tools = ReadOnlyToolProxy(self.agent) if self.agent is not None else None
        if self.agent is not None:
            self.agent.request("health")
            self.tasks = TaskProxy(self.agent)
            self.guest_ops = ReadOnlySystemProxy(self.agent)
        else:
            # Embedded testing mode, never enabled in a real guest service.
            self.tasks = GuestTaskStore(state_home / "aiws", singleton=False)
            self.guest_ops = GuestOperations(self.workspace, state_home / "aiws" / "kernel-candidates")
        self.model = LocalPlanner()

    def health(self):
        return {"system": "AIWS OS", "mode": "linux-guest",
                "agent": "systemd-user-agent" if self.agent else "embedded-test-agent",
                "agentIndependentService": self.agent is not None, "llmConnected": self.model.status()["online"],
                "agentPrivileged": False, "guestOnly": True,
                "workspace": str(self.workspace),
                "desktopInstalled": bool(shutil.which("xfce4-session")),
                "displayManagerInstalled": bool(shutil.which("lightdm")),
                "uiBundled": (self.ui / "index.html").is_file(),
                "toolCount": len(EXPOSED) + len(GUEST_OP_TOOLS), "tasksPersistent": True,
                "serviceScope": "guest-user-allowlist", "kernelChanges": "candidate-only",
                "note": "Optional offline LLM makes suggestions only; no guest privilege broker or host VM access."}

    def _remote_job(self, identifier):
        try:
            task=self.tasks.get(identifier)
        except (TaskError, AgentError):
            return None
        if not task["task"]["title"].startswith("Workbench tool: "):
            return None
        stage=task["stages"][0]
        return {"id":identifier,"tool":stage["tool"],"status":stage["state"],
                "result":stage["result"],"error":stage["error"],
                "submittedAt":task["task"]["created_at"]}

    def recent(self):
        if self.agent is not None:
            jobs=[]
            for task in self.tasks.list():
                if task["title"].startswith("Workbench tool: "):
                    job=self._remote_job(task["id"])
                    if job is not None:
                        jobs.append(job)
                if len(jobs)>=24:
                    break
            return jobs
        with self.lock:
            return [dict(x) for x in list(self.records.values())[-24:]][::-1]

    def job(self, identifier):
        if self.agent is not None:
            return self._remote_job(identifier)
        with self.lock:
            item = self.records.get(identifier)
            return dict(item) if item else None

    def submit(self, tool, args):
        spec = next((x["inputSchema"] for x in catalog() if x["name"] == tool), None)
        if tool not in EXPOSED or spec is None:
            raise ValueError("Tool is not exposed to the workbench")
        if not isinstance(args, dict) or any(k not in spec["properties"] for k in args):
            raise ValueError("Unknown tool arguments")
        if any(k not in args for k in spec["required"]):
            raise ValueError("Missing required tool arguments")
        if any(not isinstance(v, str) for v in args.values()):
            raise ValueError("Tool arguments must be strings")
        if self.agent is not None:
            stage={"key":"operation","label":tool[:160],"tool":tool,
                   "arguments":args,"dependsOn":[]}
            task=self.tasks.create("Workbench tool: "+tool,
                                   "Guest read-only workbench request",[stage])
            self.tasks.dispatch(task["task"]["id"],"operation")
            return self._remote_job(task["task"]["id"])
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



    def configure_model(self, enabled):
        # A button click only creates a pending durable DAG. The user must
        # separately approve and dispatch before any guest systemd action.
        require_guest_runtime()
        tool="service.enable" if enabled else "service.disable"
        title="Enable guest offline model" if enabled else "Disable guest offline model"
        return self.tasks.create(title,"Review guest-local model service lifecycle",
                                 [{"key":"service","label":title,"tool":tool,
                                   "arguments":{"service":"aiws-local-model.service"},
                                   "dependsOn":[]}])

    def local_guest_context(self):
        """Bounded inventory assembled by the same unprivileged guest Agent.

        Never reads file bodies, task goals, environment secrets or host data.
        Model context is optional and must not block basic workbench operation.
        """
        try:
            if self.file_tools is not None:
                tree=self.file_tools.invoke("workspace.tree", {"path": "."})
            else:
                tree=invoke("workspace.tree", {"path": "."})
            rows=self.tasks.list()
            files=[str(f)[:96] for f in tree.get("files", [])[:24]
                   if isinstance(f, str) and 0 < len(f) <= 96]
            tasks=[{"id":str(t["id"])[:48], "title":str(t["title"])[:80]}
                   for t in rows[:8] if isinstance(t, dict)
                   and isinstance(t.get("id"), str)
                   and isinstance(t.get("title"), str)]
            return {"guestFiles": files, "recentTasks": tasks}
        except (ValueError, OSError, PermissionError, AgentError, AgentUnavailable):
            return {"guestFiles": [], "recentTasks": []}

    def local_suggest(self, instruction):
        # Do not consult workspace metadata when the optional model is off.
        configured=self.model.status()["configured"]
        return self.model.suggest(
            instruction, context=self.local_guest_context() if configured else None)

    def model_plan(self, instruction):
        """Persist but do not execute a validated, read-only local model plan."""
        proposal = self.local_suggest(instruction)
        if self.agent is not None:
            # Production: independent systemd user Agent revalidates the model
            # output, owns durable state and records prompt/proposal hashes.
            return self.tasks.model_plan(instruction, proposal)
        stage = {"key": "inspect", "label": proposal["reason"][:160],
                 "tool": proposal["tool"], "arguments": proposal["arguments"],
                 "dependsOn": []}
        saved = self.tasks.create(
            ("Local proposal: " + proposal["tool"])[:160], proposal["reason"], [stage])
        self.tasks.record_model_proposal(
            saved["task"]["id"], "aiws-local", instruction, proposal)
        return self.tasks.get(saved["task"]["id"])

    def import_windows(self, payload):
        if not isinstance(payload,dict) or set(payload)!={"task"}:
            raise ValueError("Expected Windows exported WorkTask object in task field")
        return self.tasks.import_windows(payload["task"])

    def create_plan(self, payload):
        if not isinstance(payload, dict) or set(payload) != {"title", "goal", "stages"}:
            raise TaskError("Expected title, goal and stages")
        # Schema and guest-tool restrictions are independently revalidated
        # when the stage executes. Model text never becomes a command.
        return self.tasks.create(payload["title"], payload["goal"], payload["stages"])

    def dispatch_stage(self, task_id, stage_key):
        if self.agent is not None:
            return self.tasks.dispatch(task_id, stage_key)
        action = self.tasks.dispatch(task_id, stage_key)
        self.pool.submit(self._run_stage, action)
        return self.tasks.get(task_id)

    def _run_stage(self, action):
        taskid, key = action["task_id"], action["stage_key"]
        try:
            self.tasks.started(taskid, key)
            tool, args = action["tool"], action["arguments"]
            if tool in GUEST_OP_TOOLS:
                # Every system/kernel stage goes through the approved durable DAG.
                result = self.guest_ops.execute(
                    tool, args, approved=action["approvalGranted"])
            else:
                result = invoke(tool, args)
            encoded = json.dumps(result, ensure_ascii=False)
            if len(encoded) > 65536:
                result = {"truncated": True, "preview": encoded[:32000]}
            self.tasks.finished(taskid, key, result=result)
            audit(tool, args, True)
        except Exception as exc:
            try:
                self.tasks.finished(taskid, key, error=str(exc)[:240])
            except TaskError:
                pass
            audit(action["tool"], action["arguments"], False)

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
        if path == "/api/v1/workspace/tree":
            try:
                result = (app.file_tools.invoke("workspace.tree", {"path": "."})
                          if app.file_tools is not None else invoke("workspace.tree", {"path": "."}))
                if app.file_tools is None:
                    audit("workspace.tree", {"path": "."}, True)
                return self.reply(200, result)
            except AgentUnavailable as exc:
                return self.reply(503, {"error": str(exc)[:240]})
            except (ValueError, OSError, PermissionError) as exc:
                return self.reply(403, {"error": str(exc)[:240]})
        if path == "/api/v1/workspace/file":
            from urllib.parse import parse_qs
            paths = parse_qs(urlsplit(self.path).query).get("path", [])
            if len(paths) != 1 or not paths[0] or len(paths[0]) > 512:
                return self.reply(400, {"error": "One bounded guest-workspace path required"})
            try:
                result = (app.file_tools.invoke("file.read", {"path": paths[0]})
                          if app.file_tools is not None else invoke("file.read", {"path": paths[0]}))
                if app.file_tools is None:
                    audit("file.read", {"path": paths[0]}, True)
                return self.reply(200, result)
            except (ValueError, OSError, PermissionError) as exc:
                return self.reply(403, {"error": str(exc)[:240]})
        if path == "/api/v1/audit/verify":
            try:
                return self.reply(200, app.tasks.verify_audit())
            except (AgentUnavailable, AgentError) as exc:
                return self.reply(503, {"error": str(exc)[:240]})
        if path == "/api/v1/tasks":
            try:
                return self.reply(200, {"tasks": app.tasks.list()})
            except (AgentUnavailable, AgentError) as exc:
                return self.reply(503, {"error": str(exc)[:240]})
        if path.startswith("/api/v1/tasks/"):
            parts = path.strip("/").split("/")
            if len(parts) == 4:
                try:
                    return self.reply(200, app.tasks.get(parts[3]))
                except TaskError as exc:
                    return self.reply(404, {"error": str(exc)})
                except (AgentUnavailable, AgentError) as exc:
                    return self.reply(503, {"error": str(exc)[:240]})
            if len(parts) == 5 and parts[4] == "audit":
                try:
                    return self.reply(200, {"events": app.tasks.audit(parts[3])})
                except TaskError as exc:
                    return self.reply(404, {"error": str(exc)})
                except (AgentUnavailable, AgentError) as exc:
                    return self.reply(503, {"error": str(exc)[:240]})
        if path == "/api/v1/guest/services":
            try:
                return self.reply(200, {"services": [
                    app.guest_ops.execute("service.inspect", {"service": name})
                    for name in ("aiws-workbench.service", "aiws-local-model.service")]})
            except (PermissionError, ValueError, OSError) as exc:
                return self.reply(403, {"error": str(exc)[:240]})
        if path == "/api/v1/guest/kernel":
            try:
                return self.reply(200, app.guest_ops.execute("kernel.inspect", {}))
            except (PermissionError, ValueError, OSError) as exc:
                return self.reply(403, {"error": str(exc)[:240]})
        if path == "/api/v1/model/status":
            return self.reply(200, app.model.status())
        if path == "/api/v1/health":
            return self.reply(200, app.health())
        if path == "/api/v1/session":
            return self.reply(200, {"csrf": app.csrf, "mode": "linux-guest"})
        if path == "/api/v1/snapshot":
            return self.reply(200, {"health": app.health(), "jobs": app.recent(),
                                    "capabilities": [x for x in catalog() if x["name"] in EXPOSED] + guest_catalog()})
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
        path = urlsplit(self.path).path
        route = path.strip("/").split("/")
        if path not in ("/api/v1/jobs", "/api/v1/tasks", "/api/v1/model/suggest", "/api/v1/model/enable", "/api/v1/model/disable", "/api/v1/model/plan", "/api/v1/tasks/import/windows") and not (
                len(route) == 7 and route[:3] == ["api", "v1", "tasks"]
                and route[4] == "stages" and route[6] in ("approve", "dispatch")):
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
            if not isinstance(payload, dict):
                raise ValueError("Expected JSON object")
            app = self.server.application
            if path == "/api/v1/jobs":
                if set(payload) != {"tool", "arguments"}:
                    raise ValueError("Expected tool and arguments")
                result = app.submit(payload["tool"], payload["arguments"])
            elif path == "/api/v1/tasks":
                result = app.create_plan(payload)
            elif path == "/api/v1/tasks/import/windows":
                result = app.import_windows(payload)
            elif path in ("/api/v1/model/enable", "/api/v1/model/disable"):
                if payload:
                    raise ValueError("Model toggle accepts no body fields")
                result = app.configure_model(path.endswith("/enable"))
            elif path == "/api/v1/model/plan":
                if set(payload) != {"instruction"}:
                    raise ValueError("Expected instruction")
                result = app.model_plan(payload["instruction"])
            elif path == "/api/v1/model/suggest":
                if set(payload) != {"instruction"}:
                    raise ValueError("Expected instruction")
                result = app.local_suggest(payload["instruction"])
            elif route[6] == "approve":
                if payload:
                    raise ValueError("No arguments allowed for approval")
                result = app.tasks.approve(route[3], route[5])
            else:
                if payload:
                    raise ValueError("No arguments allowed for dispatch")
                result = app.dispatch_stage(route[3], route[5])
        except AgentUnavailable as exc:
            return self.reply(503, {"error": str(exc)[:240]})
        except PermissionError as exc:
            return self.reply(403, {"error": str(exc)[:240]})
        except (ValueError, KeyError, TypeError) as exc:
            return self.reply(400, {"error": str(exc)[:240]})
        return self.reply(202, result)

def make_server(workspace, ui, port=PORT, singleton=False):
    root = Path(workspace).resolve(strict=True)
    if not root.is_dir() or root in (Path("/"), Path.home()):
        raise ValueError("Dedicated workspace required")
    server = ThreadingHTTPServer((HOST, port), Handler)
    server.daemon_threads = True
    server.application = Controller(root, ui, singleton=singleton)
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
    server = make_server(workspace, ui, args.port, singleton=True)
    print("AIWS guest workbench http://" + HOST + ":" + str(server.server_port), flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()
        server.application.pool.shutdown(wait=True, cancel_futures=True)
        server.application.tasks.close()

if __name__ == "__main__":
    main()
