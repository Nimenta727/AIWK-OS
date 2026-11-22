"""Builder supervisor: runs ONE official-CLI child under a user mandate and watches it.

Division of labour (important, and stated honestly):
  * PREVENTION is the CLI's own permission system: the mandate's allowed tools and permission mode are
    passed as flags, and bypass flags are never generated. (Flag names are NOT yet verified against a real
    CLI; that is step O6.)
  * The supervisor provides LIMITS and DETECTION: wall clock, turns, token budget (from provider-reported
    usage only), refusal to continue without metering, and pausing for approval when an event shows a
    sensitive action. A tool event is seen when the CLI announces it, so a fast action may already be
    running: detection is best effort. Hard OS-level prevention (own UID, project-only write access,
    domain-allowlisted egress) is step O4.

Safety properties pinned by tests: no shell, sanitised environment, cwd = project folder, stdin closed,
own process group killed as a whole, bounded line sizes, one run at a time, a revoked/expired mandate or
exhausted budget never starts, and nothing is estimated when usage is not reported.
"""
import json
import os
from pathlib import Path
import queue
import re
import shutil
import signal
import subprocess
import threading
import time

import aiws_plans
from aiws_cli_adapters import ClaudeStreamAdapter, CodexJsonAdapter, MAX_LINE
from aiws_events import EventError, make_event, redact
from aiws_mandate import MandateError

APPROVAL_TIMEOUT = 600
UNKNOWN_USAGE_LIMIT = 3
STDERR_KEEP = 2048
SECRET_ENV = re.compile(r"(?i)token|secret|password|passwd|api[_-]?key|credential|^aws_|^azure_|^github_|^openai_|^anthropic_")
DEFAULT_ENV_ALLOW = ("PATH", "HOME", "LANG", "LC_ALL", "TERM", "TMPDIR")
PATH_TOOLS = {"Read", "Edit", "Write", "MultiEdit", "NotebookEdit"}
NETWORK_TOOLS = {"WebFetch", "WebSearch", "web_search"}
SHELL_TOOLS = {"Bash", "command"}
CATEGORY_PATTERNS = (
    ("delete", re.compile(r"(?i)\b(rm|unlink|shred|rmdir)\b|\bgit\s+clean\b")),
    ("install-dependency", re.compile(r"(?i)\b(npm|pnpm|yarn)\s+(i|install|add)\b|\bpip3?\s+install\b|\bapt(-get)?\s+install\b|\bcargo\s+(add|install)\b|\bgo\s+(get|install)\b")),
    ("git-push", re.compile(r"(?i)\bgit\s+push\b")),
    ("network", re.compile(r"(?i)\b(curl|wget|nc|ncat|ssh|scp|sftp|ftp)\b|https?://")),
    ("shell", re.compile(r"(?i)\bsudo\b|\b(bash|sh)\s+-c\b|\beval\b")),
)
FORBIDDEN_FLAGS = ("--dangerously-skip-permissions", "bypassPermissions", "dontAsk", "--yolo",
                   "--dangerously-bypass-approvals-and-sandbox", "danger-full-access")

class SupervisorError(RuntimeError):
    pass

ISOLATION_DEFAULT = {"mode": "none", "user": "aiws-builder", "proxy": "http://127.0.0.1:3128"}
SAFE_PATH = "/usr/local/bin:/usr/bin:/bin"
SIGNAL_NAMES = {signal.SIGSTOP: "STOP", signal.SIGCONT: "CONT", signal.SIGTERM: "TERM", signal.SIGKILL: "KILL"}

def validate_isolation(value):
    if not isinstance(value, dict) or set(value) - set(ISOLATION_DEFAULT):
        raise SupervisorError("isolation has unknown keys")
    out = {**ISOLATION_DEFAULT, **value}
    if (out["mode"] not in ("none", "user") or not isinstance(out["user"], str) or not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", out["user"])
            or not isinstance(out["proxy"], str) or not re.fullmatch(r"http://127\.0\.0\.1:[0-9]{2,5}", out["proxy"])):
        raise SupervisorError("isolation must be {mode: none|user, user: <account>, proxy: http://127.0.0.1:<port>}")
    return out

def load_builder_config(path=None):
    """~/.config/aiws/builder.json: strict, default DISABLED."""
    path = Path(path) if path is not None else Path.home() / ".config/aiws/builder.json"
    config = {"enabled": False, "envAllow": [], "isolation": dict(ISOLATION_DEFAULT)}
    if path.is_symlink():
        raise SupervisorError("Builder config must not be a symlink")
    if not path.exists():
        return config
    if not path.is_file() or path.stat().st_size > 2048:
        raise SupervisorError("Builder config must be a regular file up to 2 KiB")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SupervisorError("Builder config is not valid JSON") from exc
    if not isinstance(data, dict) or set(data) - set(config):
        raise SupervisorError("Builder config has unknown keys")
    if "isolation" in data:
        config["isolation"] = validate_isolation(data["isolation"])
    if "enabled" in data:
        if not isinstance(data["enabled"], bool):
            raise SupervisorError("enabled must be true or false")
        config["enabled"] = data["enabled"]
    if "envAllow" in data:
        names = data["envAllow"]
        if (not isinstance(names, list) or len(names) > 8
                or any(not isinstance(n, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,40}", n) for n in names)):
            raise SupervisorError("envAllow must be up to 8 upper-case variable names")
        config["envAllow"] = names
    return config

def claude_argv(exe, mandate, prompt, cwd):
    # Flag names follow the public CLI documentation; NOT verified against a real run (step O6).
    return [exe, "-p", prompt, "--output-format", "stream-json", "--verbose",
            "--max-turns", str(mandate["maxTurns"]), "--allowedTools", ",".join(mandate["allowedTools"]),
            "--permission-mode", mandate["permissionMode"]]

def codex_argv(exe, mandate, prompt, cwd):
    return [exe, "exec", "--json", "--sandbox", "workspace-write", "--cd", cwd, prompt]

ARGV = {"claude": ("claude", claude_argv), "codex": ("codex", codex_argv)}

def default_launcher(which=shutil.which):
    def launch(mandate, prompt, cwd):
        name, builder = ARGV[mandate["provider"]]
        exe = which(name)
        if not exe:
            raise SupervisorError("The official %s CLI is not installed on this machine" % name)
        argv = builder(exe, mandate, prompt, cwd)
        if any(flag in part for part in argv for flag in FORBIDDEN_FLAGS):
            raise SupervisorError("Refusing to build a permission-bypassing command line")
        return argv, {}
    return launch

def validate_prompt(prompt):
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 4000 or "\x00" in prompt:
        raise SupervisorError("The task text must contain 1-4000 characters")
    if prompt.lstrip().startswith("-"):
        raise SupervisorError("The task text may not start with '-'")
    return prompt.strip()

def classify_action(tool, detail, project_abs):
    """Return an approval category for a sensitive tool announcement, or None."""
    detail = detail or ""
    if tool in PATH_TOOLS and detail:
        if detail.startswith("~") or ".." in Path(detail).parts:
            return "outside-project"
        if detail.startswith("/") and not (detail == project_abs or detail.startswith(project_abs + "/")):
            return "outside-project"
    if tool in NETWORK_TOOLS or tool.startswith("mcp_"):
        return "network"
    if tool in SHELL_TOOLS:
        for category, pattern in CATEGORY_PATTERNS:
            if pattern.search(detail):
                return category
    return None

class UserIsolation:
    """Run the CLI as an unprivileged sandbox user (step O4). Everything here is a list of argv: no shell.

    Prevention comes from the OS: the user's own UID (no sudo, no groups), the nftables rule that lets that UID
    reach only the egress proxy, and ACLs that give it write access to ONE project folder (read-only .git).
    It is refused unless the firewall marker written by the root-owned firewall unit exists (fail closed).
    """
    def __init__(self, user, proxy, runner=subprocess.run, marker="/run/aiws/builder-firewall.ok", which=shutil.which,
                 sudo=None, setfacl=None, home="/var/lib/aiws-builder/home", main_user=None):
        self.user, self.proxy, self.runner, self.marker, self.which, self.home = user, proxy, runner, Path(marker), which, home
        self.sudo, self.setfacl = sudo or "sudo", setfacl or "setfacl"
        if main_user is None:
            import pwd
            main_user = pwd.getpwuid(os.getuid()).pw_name
        self.main_user = main_user
        self.touched = []

    def check(self):
        if self.marker.is_symlink() or not self.marker.is_file():
            raise SupervisorError("The builder firewall is not active (marker missing): refusing to run the builder")
        for tool in (self.sudo, self.setfacl):
            if not self.which(tool) and not Path(tool).is_file():
                raise SupervisorError("%s is required for the isolated builder" % Path(tool).name)

    def _run(self, argv, strict=True):
        try:
            result = self.runner(argv, capture_output=True, text=True, timeout=15, shell=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            if strict:
                raise SupervisorError("%s failed: %s" % (Path(argv[0]).name, type(exc).__name__)) from exc
            return False
        if result.returncode != 0 and strict:
            raise SupervisorError("%s failed (exit %s)" % (Path(argv[0]).name, result.returncode))
        return result.returncode == 0

    def _ancestors(self, project):
        mine = []
        for parent in reversed(project.parents):
            try:
                if parent != Path("/") and parent.stat().st_uid == os.getuid():
                    mine.append(parent)
            except OSError:
                continue
        return mine

    def prepare(self, project):
        self.check()
        project = Path(project)
        u, m = self.user, self.main_user
        try:
            for directory in self._ancestors(project):          # traverse only: no listing, no reading
                self._run([self.setfacl, "-m", "u:%s:--x" % u, str(directory)])
                self.touched.append(directory)
            self._run([self.setfacl, "-R", "-m", "u:%s:rwX" % u, "-m", "d:u:%s:rwX" % u,
                       "-m", "u:%s:rwX" % m, "-m", "d:u:%s:rwX" % m, str(project)])
            git = project / ".git"
            if git.is_dir() and not git.is_symlink():              # hooks and config must not be writable by the builder
                self._run([self.setfacl, "-R", "-m", "u:%s:rX" % u, "-m", "d:u:%s:rX" % u, str(git)])
        except SupervisorError:
            self.cleanup(project)
            raise

    def cleanup(self, project):
        project = Path(project)
        u, m = self.user, self.main_user
        self._run([self.setfacl, "-R", "-x", "u:" + u, "-x", "d:u:" + u, "-x", "u:" + m, "-x", "d:u:" + m, str(project)], strict=False)
        for directory in self.touched:
            self._run([self.setfacl, "-x", "u:" + u, str(directory)], strict=False)
        self.touched = []

    def wrap(self, argv):
        env = {"PATH": SAFE_PATH, "HOME": self.home, "LANG": "C.UTF-8", "TERM": "dumb", "NO_PROXY": "", "no_proxy": "",
               "HTTPS_PROXY": self.proxy, "HTTP_PROXY": self.proxy, "https_proxy": self.proxy, "http_proxy": self.proxy}
        return ([self.sudo, "-n", "-u", self.user, "--", "env", "-i"] + ["%s=%s" % kv for kv in env.items()] + list(argv))

    def signal(self, sig):
        """Signal every process of the sandbox user (one run at a time, so that is exactly the run)."""
        name = SIGNAL_NAMES.get(sig)
        if name is None:
            raise SupervisorError("Unsupported signal")
        return self._run([self.sudo, "-n", "-u", self.user, "--", "kill", "-" + name, "-1"], strict=False)

def default_isolation_factory(config):
    iso = (config or {}).get("isolation") or ISOLATION_DEFAULT
    iso = validate_isolation(iso)
    return None if iso["mode"] == "none" else UserIsolation(iso["user"], iso["proxy"])

def _read_lines(stream, sink):
    try:
        while True:
            line = stream.readline(MAX_LINE + 1)
            if not line:
                break
            if len(line) > MAX_LINE and not line.endswith(b"\n"):
                while True:                      # discard the rest of an oversized line
                    rest = stream.readline(65536)
                    if not rest or rest.endswith(b"\n"):
                        break
            sink.put(line)
    finally:
        sink.put(None)

class _Run:
    def __init__(self, run_id, mandate, adapter, proc, deadline, project_abs):
        self.id, self.mandate, self.adapter, self.proc = run_id, mandate, adapter, proc
        self.deadline, self.project_abs = deadline, project_abs
        self.tot_in = self.tot_out = None
        self.sum_in = self.sum_out = 0
        self.unknown_streak = 0
        self.stop_reason = None
        self.pending = None
        self.decision = None
        self.stderr = b""
        self.paused = False
        self.before = {"input": 0, "output": 0}
        self.iso = None

    def effective(self):
        if self.tot_in is not None or self.tot_out is not None:
            return self.tot_in or 0, self.tot_out or 0
        return self.sum_in, self.sum_out

class Supervisor:
    def _store_plans(self, run):
        """Hand plans the adapter saw to the plan store. A plan problem must never disturb the run."""
        drain = getattr(run.adapter, "drain_plans", None)
        if not self.plans or not drain:
            return
        for kind, payload in drain():
            try:
                self.plans.upsert(aiws_plans.from_cloud(run.id, kind, payload))
            except Exception:
                pass

    def __init__(self, mandates, events, workspace, launcher=None, config=None, clock=time.time, approval_timeout=APPROVAL_TIMEOUT,
                 isolation_factory=None, plans=None):
        self.mandates, self.events, self.clock = mandates, events, clock
        self.plans = plans                      # optional PlanStore: cloud plans announced by the CLI
        self.isolation_factory = isolation_factory or default_isolation_factory
        self.workspace = Path(workspace).resolve(strict=True)
        self.launcher = launcher or default_launcher()
        self.config = config or (lambda: load_builder_config())
        self.approval_timeout = approval_timeout
        self.lock = threading.RLock()
        self.active = None
        self.threads = []
        mandates.interrupt_orphans()

    # ---- helpers -------------------------------------------------------------------------
    def _emit(self, session, kind, **fields):
        try:
            self.events.append(make_event(self.clock(), "supervisor", session, kind, **fields))
        except (EventError, OSError, ValueError):
            pass

    def _env(self, extra):
        """Only an allowlist reaches the child. Secret-looking names need an explicit opt-in."""
        explicit = set(self.config().get("envAllow", []))
        env = {k: v for k, v in os.environ.items()
               if k in explicit or (k in DEFAULT_ENV_ALLOW and not SECRET_ENV.search(k))}
        env.update(extra or {})
        return env

    def _project(self, mandate):
        root = self.workspace
        target = root
        for part in Path(mandate["projectDir"]).parts:
            target = target / part
            if target.is_symlink():
                raise SupervisorError("The project folder contains a symlink")
        if not target.is_dir() or not target.resolve(strict=True).is_relative_to(root) or target.resolve(strict=True) == root:
            raise SupervisorError("The project folder no longer exists inside the workspace")
        return str(target.resolve(strict=True))

    @staticmethod
    def _adapter(provider, session, clock):
        return (ClaudeStreamAdapter if provider == "claude" else CodexJsonAdapter)(session, clock)

    # ---- public API ----------------------------------------------------------------------
    def start(self, mandate_id, prompt):
        if not self.config().get("enabled"):
            raise PermissionError("The builder is disabled (enable it in ~/.config/aiws/builder.json)")
        prompt = validate_prompt(prompt)
        mandate = self.mandates.get(mandate_id)
        if mandate["state"] != "active":
            raise PermissionError("The mandate is %s" % mandate["state"])
        remaining = self.mandates.remaining(mandate_id)
        if remaining["input"] <= 0 or remaining["output"] <= 0:
            raise PermissionError("The mandate's token budget is used up")
        with self.lock:
            if self.active is not None:
                raise SupervisorError("A build is already running; only one run at a time")
            cwd = self._project(mandate)
            argv, extra_env = self.launcher(mandate, prompt, cwd)
            if (not isinstance(argv, list) or not argv or any(not isinstance(a, str) for a in argv)):
                raise SupervisorError("Invalid command line")
            iso = self.isolation_factory(self.config())
            if iso is not None:
                iso.prepare(Path(cwd))                      # fails closed: no marker / no ACL tooling -> nothing starts
                argv, env = iso.wrap(argv), {"PATH": SAFE_PATH}
            else:
                env = self._env(extra_env)
            run_id = self.mandates.run_create(mandate_id, "")
            session = "build-" + run_id[:12]
            adapter = self._adapter(mandate["provider"], session, self.clock)
            try:
                proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
                                        close_fds=True, shell=False, bufsize=0)
            except OSError as exc:
                if iso is not None:
                    iso.cleanup(Path(cwd))
                self.mandates.run_update(run_id, state="failed", reason="could not start", ended=self.clock())
                raise SupervisorError("Could not start the CLI: %s" % type(exc).__name__) from exc
            deadline = self.clock() + mandate["wallClockMinutes"] * 60
            run = _Run(run_id, mandate, adapter, proc, deadline, cwd)
            run.iso = iso
            run.before = dict(mandate["used"])       # budget already spent by earlier runs of this mandate
            self.active = run
        self.mandates.run_update(run_id, session=session)
        self._emit("sup-" + run_id[:12], "start", detail=("mandate " + mandate["id"][:8] + " " + mandate["provider"])[:60])
        thread = threading.Thread(target=self._monitor, args=(run, session), daemon=True, name="aiws-builder")
        thread.start()
        self.threads.append(thread)
        return {"runId": run_id, "session": session}

    def stop(self, run_id, reason="user-stop"):
        with self.lock:
            run = self.active
            if run is None or run.id != run_id:
                raise SupervisorError("That run is not active")
            run.stop_reason = run.stop_reason or reason
        self._terminate(run)

    def decide(self, run_id, approve):
        with self.lock:
            run = self.active
            if run is None or run.id != run_id or run.pending is None:
                raise SupervisorError("Nothing is waiting for approval")
            run.decision = bool(approve)

    def status(self):
        with self.lock:
            run = self.active
            current = None
            if run is not None:
                used_in, used_out = run.effective()
                current = {"runId": run.id, "mandateId": run.mandate["id"], "state": "awaiting-approval" if run.pending else "running",
                           "usedInput": used_in, "usedOutput": used_out, "turns": run.adapter.turns,
                           "pending": run.pending, "deadline": run.deadline}
        isolation = (self.config().get("isolation") or ISOLATION_DEFAULT)
        return {"enabled": bool(self.config().get("enabled")), "isolation": {"mode": isolation.get("mode", "none"),
                                                                              "user": isolation.get("user", "aiws-builder")},
                "active": current,
                "runs": self.mandates.runs(5)}

    # ---- internals -----------------------------------------------------------------------
    def _signal(self, run, sig):
        """Signal the build. With user isolation the child runs as another UID, so signals go through sudo."""
        try:
            if run.iso is not None:
                return run.iso.signal(sig)
            os.killpg(run.proc.pid, sig)             # the whole group, including grandchildren
            return True
        except (ProcessLookupError, PermissionError, SupervisorError):
            return False

    def _terminate(self, run):
        proc = run.proc
        if run.paused:
            self._signal(run, signal.SIGCONT)
            run.paused = False
        if not self._signal(run, signal.SIGTERM) and proc.poll() is None and run.iso is None:
            return
        for _ in range(20):
            if proc.poll() is not None:
                break
            time.sleep(0.1)
        self._signal(run, signal.SIGKILL)

    def _pause(self, run, category, tool, detail, session):
        if self._signal(run, signal.SIGSTOP):
            run.paused = True
        run.pending = {"category": category, "tool": tool, "detail": (detail or "")[:120], "since": self.clock()}
        self.mandates.run_update(run.id, state="awaiting-approval", pending=json.dumps(run.pending))
        self._emit("sup-" + run.id[:12], "approval", status="pending", detail=category)

    def _apply(self, run, event, session):
        """Update counters from one normalised event and enforce limits. Returns a stop reason or None."""
        t = event.get("tokens")
        if event["kind"] == "usage" and t is not None:
            if t["source"] == "unknown":
                run.unknown_streak += 1
            else:
                run.unknown_streak = 0
                if t["scope"] == "total":
                    run.tot_in = max(run.tot_in or 0, t["in"] or 0)
                    run.tot_out = max(run.tot_out or 0, t["out"] or 0)
                else:
                    run.sum_in += t["in"] or 0
                    run.sum_out += t["out"] or 0
        used_in, used_out = run.effective()
        budget = run.mandate["tokenBudget"]
        before = run.before
        if before["input"] + used_in >= budget["input"] or before["output"] + used_out >= budget["output"]:
            return "token-budget"
        if run.mandate["requireMetering"] and run.unknown_streak >= UNKNOWN_USAGE_LIMIT:
            return "metering-unavailable"
        if run.adapter.turns > run.mandate["maxTurns"]:
            return "max-turns"
        if event["kind"] == "tool" and event.get("status") == "pending" and run.pending is None:
            category = classify_action(event.get("tool", ""), event.get("detail"), run.project_abs)
            if category and category in run.mandate["needApprovalFor"]:
                self._pause(run, category, event.get("tool", ""), event.get("detail"), session)
        return None

    def _resolve_approval(self, run):
        if run.pending is None:
            return
        timed_out = run.decision is None and self.clock() - run.pending["since"] > self.approval_timeout
        if run.decision is None and not timed_out:
            return
        approved = bool(run.decision)
        waited = self.clock() - run.pending["since"]
        category = run.pending["category"]
        run.pending, run.decision = None, None
        run.deadline += waited                    # time spent waiting for the user is not build time
        self._emit("sup-" + run.id[:12], "approval", status="ok" if approved else "denied", detail=category)
        self.mandates.run_update(run.id, state="running", pending=None)
        if approved:
            if self._signal(run, signal.SIGCONT):
                run.paused = False
        else:
            run.stop_reason = "approval-timeout" if timed_out else "approval-denied"
            self._terminate(run)

    def _monitor(self, run, session):
        sink = queue.Queue(maxsize=2000)
        reader = threading.Thread(target=_read_lines, args=(run.proc.stdout, sink), daemon=True)
        err = threading.Thread(target=self._drain_stderr, args=(run,), daemon=True)
        reader.start(); err.start()
        eof = False
        while True:
            self._resolve_approval(run)
            if run.stop_reason is None and run.pending is None and self.clock() > run.deadline:
                run.stop_reason = "wall-clock"
                self._terminate(run)
            try:
                line = sink.get(timeout=0.05)
            except queue.Empty:
                line = b""
            if line is None:
                eof = True
            elif line:
                events_now = run.adapter.feed(line)
                self._store_plans(run)
                for event in events_now:
                    try:
                        stored = self.events.append(event)
                    except (EventError, OSError, ValueError):
                        continue
                    if run.stop_reason is None:
                        reason = self._apply(run, stored, session)
                        if reason:
                            run.stop_reason = reason
                            self._terminate(run)
            if (eof or not reader.is_alive()) and sink.empty() and run.proc.poll() is not None:
                break
        self._finish(run, session)

    def _drain_stderr(self, run):
        try:
            while True:
                chunk = run.proc.stderr.read(4096)
                if not chunk:
                    break
                run.stderr = (run.stderr + chunk)[-STDERR_KEEP:]
        except (OSError, ValueError):
            pass

    def _finish(self, run, session):
        code = run.proc.poll()
        if code is None:
            self._terminate(run)
            code = run.proc.poll()
        for event in run.adapter.finish():
            try:
                self.events.append(event)
            except (EventError, OSError, ValueError):
                pass
        if run.iso is not None:
            run.iso.cleanup(Path(run.project_abs))
        used_in, used_out = run.effective()
        if run.stop_reason:
            state = "stopped" if run.stop_reason == "user-stop" else "killed"
            reason = run.stop_reason
        elif code == 0 and not run.adapter.failed:
            state, reason = "completed", "exit 0"
        else:
            state, reason = "failed", "exit %s%s" % (code, (": " + redact(run.stderr.decode("utf-8", "replace"), 100)) if run.stderr else "")
        self.mandates.add_usage(run.mandate["id"], used_in, used_out)
        self.mandates.run_update(run.id, state=state, reason=reason[:200], ended=self.clock(), used_in=used_in,
                                 used_out=used_out, turns=run.adapter.turns, pending=None)
        self._emit("sup-" + run.id[:12], "end", status="ok" if state == "completed" else "error", detail=(state + ": " + reason)[:120])
        with self.lock:
            if self.active is run:
                self.active = None

    def wait(self, timeout=30):
        """Test helper: wait until no run is active."""
        end = time.time() + timeout
        while time.time() < end:
            with self.lock:
                if self.active is None:
                    return True
            time.sleep(0.05)
        return False
