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
import socket
import subprocess
import threading
import time
from urllib.parse import urlsplit
from uuid import uuid4
from aiws_toolplane import audit, catalog, invoke, READ_TOOLS as PLANE_READ_TOOLS, FILE_WRITE_TOOLS, APP_LAUNCH_TOOLS
from aiws_guest_boundary import require_guest_runtime, protect_guest_workspace
from aiws_tasks import GuestTaskStore, TaskError
from aiws_guest_ops import GuestOperations, TOOLS as GUEST_OP_TOOLS, catalog as guest_catalog
from aiws_model_registry import GuestModelRegistry
from aiws_agent_client import AgentClient, TaskProxy, ReadOnlySystemProxy, ReadOnlyToolProxy, AgentUnavailable, AgentError
from aiws_local_model import LocalPlanner, LocalModelError, stages_from_proposal
from aiws_events import EventStore, EventError, SAFE_NAME, make_event
from aiws_cli_adapters import ClaudeStreamAdapter, CodexJsonAdapter, replay
import aiws_observatory
import aiws_apps
import aiws_launcher
from aiws_toolplane import _path as workspace_path, _workspace
from aiws_mandate import MandateStore, MandateError
from aiws_supervisor import Supervisor, SupervisorError, load_builder_config
from aiws_model_router import classify, after_local, build_handoff, handoff_stages, load_config, RouterError

HOST = "127.0.0.1"
PORT = 17640
READ_ONLY = PLANE_READ_TOOLS
GUEST_WRITES = FILE_WRITE_TOOLS
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
        self.events = EventStore(state_home / "aiws-observatory")
        self.mandates = MandateStore(state_home / "aiws-builder", self.workspace)
        self.supervisor = Supervisor(self.mandates, self.events, self.workspace)
        if os.environ.get("AIWS_OBSERVATORY_DEMO") == "1":
            self._seed_demo()

    def _seed_demo(self):
        """Development only: replay SYNTHETIC fixtures so the observatory can be seen without a real CLI."""
        folder = Path(__file__).resolve().parents[1] / "verify" / "fixtures" / "cli"
        existing = {s["session"] for s in self.events.sessions(200)}
        for name, cls, session in (("claude_basic", ClaudeStreamAdapter, "demo-claude"),
                                   ("codex_basic", CodexJsonAdapter, "demo-codex"),
                                   ("codex_failed", CodexJsonAdapter, "demo-codex-failed")):
            if session not in existing and (folder / (name + ".jsonl")).is_file():
                replay(folder / (name + ".jsonl"), cls(session), self.events)

    def _emit(self, agent, prefix, kind, **fields):
        """Observability must never break a request: failures are swallowed."""
        try:
            self.events.append(make_event(time.time(), agent, prefix + "-" + time.strftime("%Y%m%d"), kind, **fields))
        except (EventError, OSError, ValueError, __import__("sqlite3").Error):
            pass

    def _emit_local_call(self, outcome):
        info = self.model.take_info()
        usage = self.model.take_usage()
        if info["cached"]:                       # answered from the result cache: zero tokens, which is a fact, not "unknown"
            self._emit("local", "local", "message", detail="cache-hit")
            return
        tokens = ({"in": usage["in"], "out": usage["out"], "cacheRead": None, "cacheWrite": None,
                   "source": "reported", "scope": "delta"} if usage else {"source": "unknown", "scope": "delta"})
        self._emit("local", "local", "usage", tokens=tokens)
        notes = ("+retry" if info["retried"] else "") + ("+schema-fallback" if info["schemaFallback"] else "")
        self._emit("local", "local", "message", detail=(outcome + notes)[:60])

    # ---- AIWS Code (the IDE) ----
    IDE_LAUNCHER = "/usr/local/bin/aiws-code"
    IDE_ENV = ("HOME", "PATH", "LANG", "DISPLAY", "XAUTHORITY", "XDG_RUNTIME_DIR", "WAYLAND_DISPLAY",
               "DBUS_SESSION_BUS_ADDRESS", "AIWS_CODE_ROOT", "AIWS_CODE_PORT")

    def ide_status(self):
        root = Path(os.environ.get("AIWS_CODE_ROOT", "/opt/aiws-code"))
        installed = (root / "bin/aiws-code-server").is_file() and (root / "out/server-main.js").is_file()
        port = int(os.environ.get("AIWS_CODE_PORT", "18090"))
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.3).close()
            running = True
        except OSError:
            running = False
        version = None
        try:
            version = json.loads((root / "PROVENANCE.json").read_text(encoding="utf-8")).get("upstreamTag")
        except (OSError, ValueError, AttributeError):
            pass
        launcher = getattr(self, "ide_launcher", self.IDE_LAUNCHER)
        return {"installed": installed, "launcherPresent": Path(launcher).is_file(), "running": running,
                "version": version if isinstance(version, str) and len(version) <= 32 else None, "port": port}

    def ide_open(self):
        """Start AIWS Code (fixed command, no user-supplied arguments). Already running: nothing is started."""
        status = self.ide_status()
        if not status["installed"] or not status["launcherPresent"]:
            raise SupervisorError("AIWS Code is not installed in this image (see os/ide/README.md)")
        if status["running"]:
            return {"started": False, "running": True}
        now = time.monotonic()
        if now - getattr(self, "_ide_last", -10) < 5:
            return {"started": False, "running": False, "starting": True}
        self._ide_last = now
        env = {k: os.environ[k] for k in self.IDE_ENV if k in os.environ}
        env["AIWS_WORKSPACE"] = str(self.workspace)
        subprocess.Popen([getattr(self, "ide_launcher", self.IDE_LAUNCHER)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True, shell=False, env=env)
        return {"started": True, "running": False}

    def apps_launch(self, ident):
        if ident == "aiws-code":
            return self.ide_open()                                  # the editor keeps its own installed/running logic
        try:
            return aiws_apps.launch(ident, self.workspace)
        except FileNotFoundError as exc:
            raise SupervisorError(str(exc))

    # ---- builder (official CLI under a user mandate) ----
    @staticmethod
    def _mandate_view(m):
        keys = ("id", "provider", "projectDir", "allowedTools", "permissionMode", "maxTurns", "tokenBudget",
                "wallClockMinutes", "needApprovalFor", "requireMetering", "expires", "state", "used")
        return {k: m[k] for k in keys}

    def builder_overview(self):
        try:
            config = load_builder_config()
        except SupervisorError:
            config = {"enabled": False, "envAllow": []}
        providers = {name: {"installed": shutil.which(name) is not None} for name in ("claude", "codex")}
        return {"enabled": config["enabled"], "providers": providers,
                "mandates": [self._mandate_view(m) for m in self.mandates.active()],
                "status": self.supervisor.status()}

    def builder_grant(self, payload):
        if not load_builder_config()["enabled"]:
            raise PermissionError("The builder is disabled (enable it in ~/.config/aiws/builder.json)")
        return self._mandate_view(self.mandates.grant(payload))

    def builder_start(self, mandate_id, prompt):
        return self.supervisor.start(mandate_id, prompt)

    def observatory(self):
        overview = self.tasks.overview()
        sessions = self.events.sessions(30)
        try:
            router = load_config()
        except RouterError:
            router = {"externalEnabled": False}
        recent = [{"ts": a["ts"], "source": "task", "label": a["action"] + (" · " + a["tool"] if a["tool"] else ""),
                   "status": "error" if a["action"].endswith("failed") else "ok"} for a in overview["activity"]]
        for e in self.events.recent(12):
            recent.append({"ts": e["ts"], "source": e["agent"],
                           "label": e["kind"] + (" · " + e["tool"] if e.get("tool") else ""),
                           "status": e.get("status", "ok")})
        recent.sort(key=lambda x: -x["ts"])
        try:
            builder_enabled = load_builder_config()["enabled"]
        except SupervisorError:
            builder_enabled = False
        status = self.supervisor.status()
        active = status["active"]
        mandates = self.mandates.active()
        in_use = next((m for m in mandates if active and m["id"] == active["mandateId"]), mandates[0] if mandates else None)
        run_approvals = ([{"runId": active["runId"], **{k: active["pending"][k] for k in ("category", "tool", "detail")}}]
                         if active and active["pending"] else [])
        builder = {"state": ("disabled" if not builder_enabled else active["state"] if active else "idle"),
                   "enabled": builder_enabled, "runId": active["runId"] if active else None,
                   "turns": active["turns"] if active else 0}
        return aiws_observatory.build_summary(
            sessions=sessions, overview=overview, audit=self.tasks.verify_audit(), model=self.model.status(),
            router=router, demo=any(s["session"].startswith("demo-") for s in sessions), recent_events=recent[:16],
            builder=builder, run_approvals=run_approvals,
            budget=aiws_observatory.budget_view(in_use, active["usedInput"] if active else 0, active["usedOutput"] if active else 0))

    def health(self):
        agent_health = self.agent.request("health") if self.agent is not None else {}
        return {"system": "AIWS OS", "mode": "linux-guest",
                "agent": "systemd-user-agent" if self.agent else "embedded-test-agent",
                "agentIndependentService": self.agent is not None,
                "brokerReady": bool(agent_health.get("brokerReady")),
                "brokerScope": "same-uid-policy-only" if self.agent is not None else "embedded-test",
                "llmConnected": self.model.status()["online"],
                "agentPrivileged": False, "guestOnly": True,
                "workspace": str(self.workspace),
                "desktopInstalled": bool(shutil.which("xfce4-session")),
                "displayManagerInstalled": bool(shutil.which("lightdm")),
                "uiBundled": (self.ui / "index.html").is_file(),
                "toolCount": len(EXPOSED) + len(GUEST_OP_TOOLS), "tasksPersistent": True,
                "serviceScope": "guest-user-allowlist", "kernelChanges": "candidate-only",
                "note": "Optional offline LLM suggests only; same-UID unprivileged Broker is not mandatory OS sandboxing or host VM access."}

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
            folders=[str(d)[:94] + "/" for d in tree.get("dirs", [])[:8]
                     if isinstance(d, str) and 0 < len(d) <= 94]
            files=folders + [str(f)[:96] for f in tree.get("files", [])[:24 - len(folders)]
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

    def route_decision(self, instruction):
        """Side-effect free: no model call, no task, no network. Rules only."""
        return classify(instruction, load_config())

    @staticmethod
    def _route_record(decision):
        keys = ("route", "rule", "agent", "instructionSha256", "forbidden", "externalAllowed", "externalEnabled")
        return {k: decision[k] for k in keys}

    def model_plan(self, instruction):
        """Route first (rules), then persist a validated local model plan. Read-only leading
        stages run automatically; every file-changing stage waits for an explicit approval."""
        decision = self.route_decision(instruction)
        self._emit("router", "router", "message", detail=("%s/%s" % (decision["route"], decision["rule"]))[:60])
        if decision["route"] != "local":
            # Not a local-model task: nothing is sent anywhere; the user decides what to do next.
            return {"routed": decision["route"], "decision": decision, "executed": False}
        try:
            proposal = self.local_suggest(instruction)
        except LocalModelError as exc:
            message = str(exc)
            self._emit_local_call("failed")
            outcome = "unavailable" if ("unavailable" in message.lower() or "No local model" in message) else "invalid"
            return {"routed": "local-failed", "decision": decision, "outcome": outcome,
                    "followUp": after_local(decision, outcome), "error": message[:200], "executed": False}
        self._emit_local_call("refused" if proposal["tool"] == "refuse" else "planned")
        if proposal["tool"] == "refuse":
            # Explicit refusals are terminal decisions, never DAG tool nodes, never escalated.
            return {"refused": True, "proposal": proposal, "executed": False,
                    "decision": decision, "followUp": after_local(decision, "refused")}
        if self.agent is not None:
            # Production: independent systemd user Agent revalidates the raw model output,
            # computes fingerprints, owns durable state and records prompt/proposal hashes.
            doc = self.tasks.model_plan(instruction, LocalPlanner.canonical(proposal))
        else:
            stages = stages_from_proposal(proposal, lambda p: invoke("file.stat", {"path": p}))
            title = ("Local plan: %d steps" % len(stages)) if "steps" in proposal \
                else ("Local proposal: " + proposal["tool"])
            saved = self.tasks.create(title[:160], proposal["reason"], stages)
            self.tasks.record_model_proposal(
                saved["task"]["id"], "aiws-local", instruction, proposal)
            doc = self.tasks.get(saved["task"]["id"])
        try:
            doc = self.tasks.route(doc["task"]["id"], self._route_record(decision)) if self.agent is not None \
                else self.tasks.record_route(doc["task"]["id"], self._route_record(decision))
        except TaskError:
            pass   # routing evidence is best effort; the plan itself is already durable
        self._autorun_reads(doc["task"]["id"])
        return doc

    def create_handoff(self, instruction, agent):
        """Prepare (never send) an external-CLI handoff file. Needs config, a permitted request
        and, afterwards, explicit approval of the file-writing stages."""
        config = load_config()
        decision = classify(instruction, config)
        if agent not in ("claude", "codex", "dual"):
            raise ValueError("Unknown external agent")
        wanted = ("claude", "codex") if agent == "dual" else (agent,)
        if (not config["externalEnabled"] or not decision["externalAllowed"]
                or any(not config["providers"].get(name) for name in wanted)):
            raise PermissionError("External handoff is not permitted for this request or configuration")
        tree = self.file_tools.invoke("workspace.tree", {"path": "."}) if self.file_tools is not None \
            else invoke("workspace.tree", {"path": "."})
        handoff = build_handoff(instruction, agent, decision, [f for f in tree.get("files", []) if isinstance(f, str)])
        try:
            (self.file_tools.invoke("file.stat", {"path": "handoff"}) if self.file_tools is not None
             else invoke("file.stat", {"path": "handoff"}))
            folder_exists = True
        except (ValueError, OSError):
            folder_exists = False
        saved = self.tasks.create(("Handoff for " + agent)[:160],
                                  "Prepare a reviewable handoff file for an official CLI. Nothing is sent.",
                                  handoff_stages(handoff, folder_exists))
        record = {**self._route_record(decision), "route": "external", "rule": "L2-handoff", "agent": agent}
        try:
            self.tasks.route(saved["task"]["id"], record) if self.agent is not None \
                else self.tasks.record_route(saved["task"]["id"], record)
        except TaskError:
            pass
        return {"task": saved["task"], "stages": saved["stages"], "handoff": {
            "path": handoff["path"], "sha256": handoff["sha256"], "dataShared": handoff["dataShared"]}}

    def _autorun_reads(self, task_id):
        """Run the leading local read-only stages; stop at the first stage that needs approval."""
        def work():
            try:
                for stage in self.tasks.get(task_id)["stages"]:
                    if stage["tool"] not in PLANE_READ_TOOLS:
                        return
                    if stage["state"] != "pending":
                        continue
                    self.dispatch_stage(task_id, stage["stage_key"])
                    deadline = time.time() + 60
                    state = "queued"
                    while time.time() < deadline and state in ("queued", "running"):
                        time.sleep(0.1)
                        state = next(s["state"] for s in self.tasks.get(task_id)["stages"]
                                     if s["stage_key"] == stage["stage_key"])
                    if state != "completed":
                        return
            except Exception:  # background convenience must never take the server down
                return
        threading.Thread(target=work, daemon=True, name="aiws-autorun").start()

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
            elif tool in APP_LAUNCH_TOOLS:
                # Stand-alone workbench (no separate Agent): this process HAS the display and `dispatch` already
                # required the user's persisted approval.
                result = aiws_apps.launch(aiws_apps.require_launchable(args["id"]), self.workspace)
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
                         "frame-src 'self' http://127.0.0.1:* http://localhost:*; "
                         "frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(data)

    RAW_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp",
                 ".svg": "image/svg+xml", ".pdf": "application/pdf", ".html": "text/html; charset=utf-8", ".htm": "text/html; charset=utf-8"}
    RAW_MAX = 20 * 1024 * 1024

    def reply_raw(self, relative):
        """Serve ONE workspace file for the viewer. Allowlisted types only; documents that can run script are sandboxed
        into an opaque origin (no access to this service's API) with no network."""
        try:
            path = workspace_path(_workspace(), relative)
            media = self.RAW_TYPES.get(path.suffix.lower())
            if media is None or not path.is_file() or path.stat().st_size > self.RAW_MAX:
                return self.reply(415, {"error": "Not a previewable file type or too large"})
            body = path.read_bytes()
        except (ValueError, OSError, PermissionError) as exc:
            return self.reply(403, {"error": str(exc)[:240]})
        scripted = media.startswith("text/html") or media.startswith("image/svg")
        csp = ("sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; "
               "font-src data:; frame-ancestors 'self'" if scripted else
               "default-src 'none'; style-src 'unsafe-inline'; img-src data:; frame-ancestors 'self'")
        self.send_response(200)
        self.send_header("Content-Type", media)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", csp)
        self.end_headers()
        self.wfile.write(body)

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
        if path in ("/api/v1/workspace/stat", "/api/v1/workspace/trash"):
            from urllib.parse import parse_qs
            if path.endswith("/stat"):
                paths = parse_qs(urlsplit(self.path).query).get("path", [])
                if len(paths) != 1 or not paths[0] or len(paths[0]) > 512:
                    return self.reply(400, {"error": "One bounded guest-workspace path required"})
                tool, args = "file.stat", {"path": paths[0]}
            else:
                tool, args = "file.trashList", {}
            try:
                result = (app.file_tools.invoke(tool, args)
                          if app.file_tools is not None else invoke(tool, args))
                if app.file_tools is None:
                    audit(tool, args, True)
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
        if path == "/api/v1/workspace/doc":
            from urllib.parse import parse_qs
            docs = parse_qs(urlsplit(self.path).query).get("path", [])
            if len(docs) != 1 or not docs[0] or len(docs[0]) > 512:
                return self.reply(400, {"error": "One bounded guest-workspace path required"})
            try:
                result = (app.file_tools.invoke("doc.text", {"path": docs[0]})
                          if app.file_tools is not None else invoke("doc.text", {"path": docs[0]}))
                if app.file_tools is None:
                    audit("doc.text", {"path": docs[0]}, True)
                return self.reply(200, result)
            except AgentUnavailable as exc:
                return self.reply(503, {"error": str(exc)[:240]})
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
                    for name in ("aiws-workbench.service", "aiws-agent.service",
                                 "aiws-permission-broker.service", "aiws-local-model.service")]})
            except (PermissionError, ValueError, OSError) as exc:
                return self.reply(403, {"error": str(exc)[:240]})
        if path == "/api/v1/guest/kernel":
            try:
                return self.reply(200, app.guest_ops.execute("kernel.inspect", {}))
            except (PermissionError, ValueError, OSError) as exc:
                return self.reply(403, {"error": str(exc)[:240]})
        if path == "/api/v1/observatory":
            try:
                return self.reply(200, app.observatory())
            except (AgentUnavailable, AgentError) as exc:
                return self.reply(503, {"error": str(exc)[:240]})
        if path == "/api/v1/observatory/events":
            from urllib.parse import parse_qs
            query = parse_qs(urlsplit(self.path).query)
            session = (query.get("session") or [""])[0]
            try:
                after = int((query.get("after") or ["0"])[0])
            except ValueError:
                return self.reply(400, {"error": "after must be an integer"})
            if not SAFE_NAME.match(session) or after < 0:
                return self.reply(400, {"error": "A valid session id is required"})
            return self.reply(200, {"session": session, "events": app.events.events(session, after=after, limit=200)})
        if path == "/api/v1/ide":
            return self.reply(200, app.ide_status())
        if path == "/api/v1/apps":
            return self.reply(200, {"apps": aiws_apps.listing()})
        if path == "/api/v1/workspace/raw":
            from urllib.parse import parse_qs
            raws = parse_qs(urlsplit(self.path).query).get("path", [])
            if len(raws) != 1 or not raws[0] or len(raws[0]) > 512:
                return self.reply(400, {"error": "One bounded guest-workspace path required"})
            return self.reply_raw(raws[0])
        if path == "/api/v1/builder":
            return self.reply(200, app.builder_overview())
        if path == "/api/v1/route/config":
            try:
                config = load_config()
            except RouterError as exc:
                return self.reply(403, {"error": str(exc)[:240]})
            return self.reply(200, {"config": config, "file": "~/.config/aiws/routes.json", "editableInUi": False})
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
        if path not in ("/api/v1/jobs", "/api/v1/tasks", "/api/v1/model/suggest", "/api/v1/model/enable", "/api/v1/model/disable", "/api/v1/model/plan", "/api/v1/route", "/api/v1/route/handoff", "/api/v1/tasks/import/windows", "/api/v1/builder/mandates", "/api/v1/builder/runs", "/api/v1/ide/open", "/api/v1/apps/launch") and not (
                len(route) == 6 and route[:3] == ["api", "v1", "builder"] and (
                    (route[3] == "mandates" and route[5] == "revoke") or
                    (route[3] == "runs" and route[5] in ("stop", "approve", "deny")))) and not (
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
            elif path == "/api/v1/apps/launch":
                if set(payload) != {"id"}:
                    raise ValueError("Expected the application id only")
                result = app.apps_launch(payload["id"])
            elif path == "/api/v1/ide/open":
                if payload:
                    raise ValueError("No arguments allowed")
                result = app.ide_open()
            elif path == "/api/v1/builder/mandates":
                result = app.builder_grant(payload)
            elif path == "/api/v1/builder/runs":
                if set(payload) != {"mandateId", "prompt"}:
                    raise ValueError("Expected mandateId and prompt")
                result = app.builder_start(payload["mandateId"], payload["prompt"])
            elif route[:3] == ["api", "v1", "builder"]:
                if payload:
                    raise ValueError("No arguments allowed")
                if route[3] == "mandates":
                    result = app._mandate_view(app.mandates.revoke(route[4]))
                elif route[5] == "stop":
                    app.supervisor.stop(route[4])
                    result = {"stopped": True}
                else:
                    app.supervisor.decide(route[4], route[5] == "approve")
                    result = {"decided": route[5]}
            elif path == "/api/v1/route":
                if set(payload) != {"instruction"}:
                    raise ValueError("Expected instruction")
                result = app.route_decision(payload["instruction"])
            elif path == "/api/v1/route/handoff":
                if set(payload) != {"instruction", "agent"}:
                    raise ValueError("Expected instruction and agent")
                result = app.create_handoff(payload["instruction"], payload["agent"])
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
        except SupervisorError as exc:
            return self.reply(409, {"error": str(exc)[:240]})
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
    try:                                              # the desktop launcher for approved `app.launch` stages
        state = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
        aiws_launcher.start_in_thread(aiws_launcher.LauncherPolicy(state / "aiws" / "tasks.sqlite3", workspace.resolve(strict=True)))
    except (OSError, PermissionError) as exc:
        print("AIWS desktop launcher unavailable: " + type(exc).__name__, flush=True)
    print("AIWS guest workbench http://" + HOST + ":" + str(server.server_port), flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()
        server.application.pool.shutdown(wait=True, cancel_futures=True)
        server.application.tasks.close()

if __name__ == "__main__":
    main()
