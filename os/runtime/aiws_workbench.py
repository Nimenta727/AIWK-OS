"""AIWS OS guest-local workbench with persistent guest task/DAG control (the application layer).

An unprivileged single-user prototype; not an autonomous model or privileged broker.
"""
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
import argparse
import json
import os
import re
import stat
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import threading
import time
from uuid import uuid4
from aiws_toolplane import audit, catalog, invoke, READ_TOOLS as PLANE_READ_TOOLS, APP_LAUNCH_TOOLS
from aiws_guest_boundary import require_guest_runtime, protect_guest_workspace
from aiws_tasks import GuestTaskStore, TaskError
from aiws_guest_ops import GuestOperations, TOOLS as GUEST_OP_TOOLS, catalog as guest_catalog
from aiws_agent_client import AgentClient, TaskProxy, ReadOnlySystemProxy, ReadOnlyToolProxy, AgentUnavailable, AgentError
from aiws_local_model import LocalPlanner, LocalModelError, stages_from_proposal
from aiws_events import EventStore, EventError, make_event
from aiws_cli_adapters import ClaudeStreamAdapter, CodexJsonAdapter, replay
import aiws_observatory
import aiws_apps
import aiws_system
import aiws_capabilities
import aiws_assistant
import aiws_changes
import aiws_plans
import aiws_sysverify
import aiws_secrets
import aiws_deepseek
import aiws_preview
import aiws_launcher
from aiws_mandate import MandateStore
from aiws_supervisor import Supervisor, SupervisorError, load_builder_config
from aiws_model_router import classify, after_local, build_handoff, handoff_stages, load_config, RouterError

# The HTTP layer (request checks, the route table) is aiws_workbench_http.py; this module is the application.
from aiws_workbench_http import Handler, HOST, EXPOSED, ASSETS  # noqa: F401  (re-exported for callers and tests)

PORT = 17640
READ_ONLY = PLANE_READ_TOOLS

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
        self.system = aiws_system.SystemControls()
        self.memory = aiws_capabilities.MemoryStore(state_home / "aiws" / "memory.jsonl")
        self.capabilities = self._build_capabilities()
        skills_dir = Path(os.environ.get("AIWS_SKILLS_DIR", self.SKILLS_DIR))
        try:
            pinned = {k: v for k, v in json.loads((skills_dir / "manifest.json").read_text(encoding="utf-8")).items() if isinstance(k, str) and isinstance(v, str)}
        except (OSError, ValueError, AttributeError):
            pinned = {}
        self.assistant = aiws_assistant.Assistant(
            state_home / "aiws", self.file_tools.invoke if self.file_tools is not None else invoke, catalog(), self._persist_proposal,
            emit=self._assistant_event, enabled=lambda: self.model.status()["configured"], skills_dir=skills_dir, pinned=pinned,
            system_plugins_dir=os.environ.get("AIWS_PLUGINS_DIR", aiws_assistant.aiws_plugins.SYSTEM_DIR))
        self.events = EventStore(state_home / "aiws-observatory")
        self.mandates = MandateStore(state_home / "aiws-builder", self.workspace)
        self.plans = aiws_plans.PlanStore(state_home / "aiws" / "plans.json")
        self.results = aiws_plans.ResultStore(state_home / "aiws" / "results.json")
        self.preview = aiws_preview.PreviewManager(self.workspace, self._preview_dir)
        self.supervisor = Supervisor(self.mandates, self.events, self.workspace, plans=self.plans, results=self.results)
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

    def ide_open(self, server_only=False):
        """Start AIWS Code (fixed command, no user-supplied arguments). Already running: nothing is started.
        server_only starts just the loopback server, for the tab embedded in the workbench; otherwise the launcher also opens its own window."""
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
        subprocess.Popen([getattr(self, "ide_launcher", self.IDE_LAUNCHER)] + (["--server-only"] if server_only else []), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True, shell=False, env=env)
        return {"started": True, "running": False}

    SKILLS_DIR = "/usr/local/share/aiws/skills"

    def _build_capabilities(self):
        docs = [(t["name"], t["description"]) for t in catalog() if t["name"] in EXPOSED]
        docs += [(t["name"], t["description"]) for t in guest_catalog()]
        skills = Path(os.environ.get("AIWS_SKILLS_DIR", self.SKILLS_DIR))
        pinned = None
        try:
            pinned = {k: v for k, v in json.loads((skills / "manifest.json").read_text(encoding="utf-8")).items()
                      if isinstance(k, str) and isinstance(v, str)}
        except (OSError, ValueError, AttributeError):
            pinned = {}                                   # no readable manifest: no trusted skill is loaded
        return aiws_capabilities.Capabilities(docs, skill_dirs=[(skills, True)], pinned=pinned, memory=self.memory)

    def memory_op(self, payload):
        try:
            if set(payload) == {"forget"}:
                result = self.memory.forget(str(payload["forget"])[:32])
            elif set(payload) <= {"text", "kind"} and "text" in payload:
                result = self.memory.add(payload["text"], payload.get("kind", "fact"))
            else:
                raise ValueError("Expected {text, kind} or {forget}")
        except aiws_capabilities.CapabilityError as exc:
            raise SupervisorError(str(exc))
        self.capabilities.refresh()
        return result

    @staticmethod
    def _system_verify():
        """Result of the boot-time system file check (bounded read; None when it has not run, e.g. outside the image)."""
        try:
            with open(aiws_sysverify.RESULT, "rb") as fh:
                data = json.loads(fh.read(65536))
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        return {"ok": data.get("ok") is True, "modified": [str(x)[:200] for x in (data.get("modified") or [])[:20]],
                "missing": [str(x)[:200] for x in (data.get("missing") or [])[:20]],
                "unlisted": [str(x)[:200] for x in (data.get("unlisted") or [])[:20]], "error": str(data.get("error", ""))[:120] or None}

    def system_op(self, kind, payload):
        """Display / input method / network / power. Strict per-operation payloads, a shared 2 s rate limit."""
        now = time.monotonic()
        if now - getattr(self, "_sys_last", -10) < 2:
            raise ValueError("Too many system operations; wait a moment")
        self._sys_last = now
        shapes = {"display": {"output", "mode"}, "input": {"name"}, "network": {"ssid", "password"},
                  "power": {"action", "confirm"}}
        if kind not in shapes or not set(payload) <= shapes[kind] or not payload:
            raise ValueError("Unexpected fields for this system operation")
        try:
            if kind == "display":
                return self.system.display_set(payload.get("output"), payload.get("mode"))
            if kind == "input":
                return self.system.ime_set(payload.get("name"))
            if kind == "network":
                return self.system.network_connect(payload.get("ssid"), payload.get("password"))
            return self.system.power(payload.get("action"), payload.get("confirm"))
        except aiws_system.SystemError_ as exc:
            raise SupervisorError(str(exc))

    @staticmethod
    def _ide_token():
        """The access token the launcher wrote. Read only if the file is private, ours, a regular file and small (same rules as the key file)."""
        runtime = os.environ.get("XDG_RUNTIME_DIR") or str(Path.home() / ".local/share/aiws-code")
        path = Path(runtime) / "aiws-code.token"
        try:
            st = os.lstat(path)
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077 or st.st_size > 256:
                raise SupervisorError("The AIWS Code access token file is unsafe")
            token = path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            raise SupervisorError("The AIWS Code access token is missing")
        except OSError:
            raise SupervisorError("The AIWS Code access token could not be read")
        if not re.fullmatch(r"[0-9a-f]{16,128}", token):
            raise SupervisorError("The AIWS Code access token is unsafe")
        return token

    def ide_session(self, rel):
        """URL for the IDE tab: the loopback server, the access token and a folder chosen with the platform's path rules."""
        status = self.ide_status()
        if not status["installed"]:
            raise SupervisorError("AIWS Code is not installed in this image (see os/ide/README.md)")
        if not status["running"]:
            raise SupervisorError("AIWS Code is not running")
        try:
            folder = aiws_changes.project_dir(self.workspace, rel or ".")
        except aiws_changes.ChangesError as exc:
            raise SupervisorError(str(exc))
        from urllib.parse import quote
        return {"url": "http://127.0.0.1:%d/?tkn=%s&folder=%s" % (status["port"], self._ide_token(), quote(str(folder), safe="/")), "port": status["port"], "folder": str(folder)}

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
        return {**{k: m[k] for k in keys}, **{k: m[k] for k in ("model", "thinking", "effort", "planApproval") if k in m}}

    def builder_overview(self):
        try:
            config = load_builder_config()
        except SupervisorError:
            config = {"enabled": False, "envAllow": []}
        providers = {name: {"installed": shutil.which(name) is not None} for name in ("claude", "codex")}
        key = aiws_secrets.status()
        providers["deepseek"] = {"installed": key["configured"], "keyConfigured": key["configured"], "keyProblem": key["problem"], "models": list(aiws_deepseek.MODELS)}
        return {"enabled": config["enabled"], "providers": providers,
                "mandates": [self._mandate_view(m) for m in self.mandates.active()],
                "status": self.supervisor.status(), "lastResult": self.results.last()}

    def builder_grant(self, payload):
        if not load_builder_config()["enabled"]:
            raise PermissionError("The builder is disabled (enable it in ~/.config/aiws/builder.json)")
        return self._mandate_view(self.mandates.grant(payload))

    def builder_start(self, mandate_id, prompt, language="zh"):
        return self.supervisor.start(mandate_id, prompt, language)

    @staticmethod
    def _preview_dir(root, rel):
        try:
            return aiws_changes.project_dir(root, rel)
        except aiws_changes.ChangesError as exc:
            raise aiws_preview.PreviewError(str(exc))

    def preview_op(self, action, payload):
        """Start / stop the static project preview. Same 2-second limiter as the other system-level actions."""
        now = time.monotonic()
        if now - getattr(self, "_preview_last", -10) < 1:
            raise ValueError("Too many system operations; wait a moment")
        self._preview_last = now
        try:
            if action == "stop" and not payload:
                return self.preview.stop()
            if action == "start" and set(payload) == {"path"} and isinstance(payload["path"], str):
                return self.preview.start(payload["path"])
        except aiws_preview.PreviewError as exc:
            raise SupervisorError(str(exc))
        raise ValueError("Unexpected fields for this system operation")

    def cloud_key(self, payload):
        """Save or clear the DeepSeek key. The key is only ever written to the private config file; it is never echoed back."""
        now = time.monotonic()
        if now - getattr(self, "_key_last", -10) < 2:
            raise ValueError("Too many system operations; wait a moment")
        self._key_last = now
        try:
            if payload == {"clear": True}:
                return aiws_secrets.clear()
            if set(payload) == {"key"}:
                return aiws_secrets.save(payload["key"], forbidden_roots=[self.workspace])
        except aiws_secrets.SecretError as exc:
            raise SupervisorError(str(exc))
        raise ValueError("Expected {key} or {clear: true}")

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
        run_approvals = ([{"runId": active["runId"], **{k: active["pending"][k] for k in ("category", "tool", "detail")},
                           "terminates": not active["pending"].get("sync")}]
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
                "desktopInstalled": bool(shutil.which("openbox")),
                "systemVerify": self._system_verify(),
                "workDisk": os.path.ismount("/srv/aiws-work"),
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



    def route_config(self):
        """The router config as the route page shows it (read-only in the UI)."""
        return load_config()

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
        return self._persist_proposal(instruction, proposal, decision)

    def _persist_proposal(self, instruction, proposal, decision=None):
        """A validated proposal -> a durable task whose changing steps wait for approval. The one path for the one-shot planner AND the
        assistant, so both end up in the same plan review area. Accepts the validated or the canonical shape."""
        proposal = LocalPlanner.canonical(proposal)
        if self.agent is not None:
            # Production: independent systemd user Agent revalidates the raw model output,
            # computes fingerprints, owns durable state and records prompt/proposal hashes.
            doc = self.tasks.model_plan(instruction, proposal)
        else:
            stages = stages_from_proposal(proposal, lambda p: invoke("file.stat", {"path": p}))
            title = ("Local plan: %d steps" % len(stages)) if "steps" in proposal \
                else ("Local proposal: " + proposal["tool"])
            saved = self.tasks.create(title[:160], proposal["reason"], stages)
            self.tasks.record_model_proposal(
                saved["task"]["id"], "aiws-local", instruction, proposal)
            doc = self.tasks.get(saved["task"]["id"])
        if decision is not None:
            try:
                doc = self.tasks.route(doc["task"]["id"], self._route_record(decision)) if self.agent is not None \
                    else self.tasks.record_route(doc["task"]["id"], self._route_record(decision))
            except TaskError:
                pass   # routing evidence is best effort; the plan itself is already durable
        self._autorun_reads(doc["task"]["id"])
        return doc

    def _assistant_event(self, event):
        mapped = aiws_assistant.observatory_events(event)
        if mapped is not None:
            kind, fields = mapped
            self._emit("local", "assistant", kind, **fields)

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
