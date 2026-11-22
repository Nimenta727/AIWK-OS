"""Authorisation mandate: the user's one-time grant for a builder run. Validation + SQLite store.

A mandate bounds WHAT a builder (official CLI) may do. It can only NARROW what is possible:
categories that are forbidden system-wide (unrestricted shell, bypassing approvals, root, network
downloads of arbitrary content, permanent deletion, ...) can never be granted by any mandate.

Pure standard library. No process, socket or model call here.
"""
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import threading
import time
import uuid

from aiws_cloud_agent import NATIVE_TOOLS
from aiws_deepseek import EFFORTS, MODELS

PROVIDERS = ("claude", "codex", "deepseek")
NATIVE_ONLY = ("model", "thinking", "effort", "planApproval")   # fields that only the in-house DeepSeek runner understands
PERMISSION_MODES = ("default", "plan", "acceptEdits")       # never "bypassPermissions" / "dontAsk"
APPROVAL_CATEGORIES = ("delete", "install-dependency", "git-push", "network", "shell", "outside-project", "write")
MAX_TURNS_LIMIT, MAX_MINUTES_LIMIT, MAX_TOKENS_LIMIT = 200, 480, 50_000_000
MAX_EXPIRY_SECONDS = 7 * 24 * 3600
TOOL_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}(\([^()\x00-\x1f]{1,80}\))?\Z")
UNRESTRICTED = {"Bash", "bash", "*", "Shell", "shell", "Bash(*)", "Bash(:*)"}
DANGEROUS_PATTERN = re.compile(r"(?i)\b(sudo|su|rm|dd|mkfs|chmod|chown|curl|wget|nc|ncat|ssh|scp|eval|exec)\b|[;&|`$<>]")

class MandateError(ValueError):
    pass

def _int(value, low, high, name):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise MandateError(name + " must be an integer between %d and %d" % (low, high))
    return value

def validate_mandate(data, workspace, now=None):
    """Return a normalised mandate dict or raise MandateError. `workspace` is the guest workspace root."""
    now = time.time() if now is None else now
    allowed = {"provider", "projectDir", "allowedTools", "permissionMode", "maxTurns", "tokenBudget",
               "wallClockMinutes", "needApprovalFor", "requireMetering", "expiresInMinutes", *NATIVE_ONLY}
    if not isinstance(data, dict) or set(data) - allowed:
        raise MandateError("Unknown mandate fields")
    if data.get("provider") not in PROVIDERS:
        raise MandateError("provider must be claude, codex or deepseek")
    native = data["provider"] == "deepseek"
    if not native and any(k in data for k in NATIVE_ONLY):
        raise MandateError("model, thinking, effort and planApproval are only for the deepseek provider")
    project = data.get("projectDir")
    if not isinstance(project, str) or not project or len(project) > 200 or "\\" in project or project.startswith("/"):
        raise MandateError("projectDir must be a relative workspace folder")
    parts = Path(project).parts
    if any(p in ("..", ".", ".git", ".ssh", ".aiws-trash", "handoff") for p in parts):
        raise MandateError("projectDir may not use protected or parent folders")
    root = Path(workspace).resolve(strict=True)
    target = root.joinpath(*parts)
    cursor = root
    for part in parts:                      # no symlink anywhere on the path
        cursor = cursor / part
        if cursor.is_symlink():
            raise MandateError("projectDir may not contain symlinks")
    if not target.is_dir() or target.resolve(strict=True) == root or not target.resolve(strict=True).is_relative_to(root):
        raise MandateError("projectDir must be an existing sub-folder of the workspace")
    tools = data.get("allowedTools")
    if not isinstance(tools, list) or not 1 <= len(tools) <= (len(NATIVE_TOOLS) if native else 16):
        raise MandateError("allowedTools needs 1-%d entries" % (len(NATIVE_TOOLS) if native else 16))
    clean_tools = []
    for tool in tools:
        if native:                                   # the runner has no shell at all: only its own named tools, never patterns
            if tool not in NATIVE_TOOLS:
                raise MandateError("Invalid tool entry")
            if tool not in clean_tools:
                clean_tools.append(tool)
            continue
        if not isinstance(tool, str) or not TOOL_NAME.match(tool):
            raise MandateError("Invalid tool entry")
        if tool in UNRESTRICTED:
            raise MandateError("An unrestricted shell can never be granted; use a specific pattern such as Bash(npm test)")
        if "(" in tool and DANGEROUS_PATTERN.search(tool[tool.index("("):]):
            raise MandateError("Tool pattern contains a forbidden command or shell syntax")
        if tool not in clean_tools:
            clean_tools.append(tool)
    mode = data.get("permissionMode", "default")
    if mode not in PERMISSION_MODES:
        raise MandateError("permissionMode may not bypass permission prompts")
    budget = data.get("tokenBudget")
    if not isinstance(budget, dict) or set(budget) != {"input", "output"}:
        raise MandateError("tokenBudget needs input and output limits")
    approvals = data.get("needApprovalFor", ["delete", "install-dependency", "git-push", "network", "shell", "outside-project"])
    if (not isinstance(approvals, list) or len(set(approvals)) != len(approvals)
            or any(a not in APPROVAL_CATEGORIES for a in approvals)):
        raise MandateError("Invalid needApprovalFor categories")
    for required in ("network", "shell", "outside-project"):
        if required not in approvals:
            raise MandateError("The %s approval cannot be switched off" % required)
    metering = data.get("requireMetering", True)
    if not isinstance(metering, bool):
        raise MandateError("requireMetering must be true or false")
    minutes = _int(data.get("expiresInMinutes", 24 * 60), 1, MAX_EXPIRY_SECONDS // 60, "expiresInMinutes")
    extra = {}
    if native:
        model = data.get("model", MODELS[0])
        if model not in MODELS:
            raise MandateError("model is not one of the supported DeepSeek models")
        effort = data.get("effort", "high")
        if effort not in EFFORTS:
            raise MandateError("effort must be low, high or max")
        thinking, plan_approval = data.get("thinking", True), data.get("planApproval", True)
        if not isinstance(thinking, bool) or not isinstance(plan_approval, bool):
            raise MandateError("thinking and planApproval must be true or false")
        extra = {"model": model, "thinking": thinking, "effort": effort, "planApproval": plan_approval}
    return {**extra, "provider": data["provider"], "projectDir": "/".join(parts), "allowedTools": clean_tools,
            "permissionMode": mode, "maxTurns": _int(data.get("maxTurns"), 1, MAX_TURNS_LIMIT, "maxTurns"),
            "tokenBudget": {"input": _int(budget["input"], 1, MAX_TOKENS_LIMIT, "tokenBudget.input"),
                            "output": _int(budget["output"], 1, MAX_TOKENS_LIMIT, "tokenBudget.output")},
            "wallClockMinutes": _int(data.get("wallClockMinutes"), 1, MAX_MINUTES_LIMIT, "wallClockMinutes"),
            "needApprovalFor": sorted(approvals), "requireMetering": metering,
            "expires": int(now + minutes * 60)}

class MandateStore:
    def __init__(self, folder, workspace, clock=time.time):
        self.folder = Path(folder)
        if not self.folder.is_absolute() or self.folder.is_symlink():
            raise MandateError("Mandate store must be an absolute, non-symlink directory")
        self.folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.folder.is_symlink() or self.folder.stat().st_mode & 0o077:
            raise MandateError("Mandate store directory must be mode 0700")
        self.workspace, self.clock = Path(workspace), clock
        path = self.folder / "mandates.sqlite3"
        if path.is_symlink():
            raise MandateError("Mandate database symlinks are forbidden")
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, timeout=10, isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS mandates(
            id TEXT PRIMARY KEY, body TEXT NOT NULL, sha256 TEXT NOT NULL, created REAL NOT NULL,
            revoked REAL, used_in INTEGER NOT NULL DEFAULT 0, used_out INTEGER NOT NULL DEFAULT 0)""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS runs(
            id TEXT PRIMARY KEY, mandate_id TEXT NOT NULL, session TEXT NOT NULL, state TEXT NOT NULL,
            reason TEXT, started REAL NOT NULL, ended REAL, used_in INTEGER NOT NULL DEFAULT 0,
            used_out INTEGER NOT NULL DEFAULT 0, turns INTEGER NOT NULL DEFAULT 0, pending TEXT)""")

    def close(self):
        with self.lock:
            self.db.close()

    def grant(self, data):
        body = validate_mandate(data, self.workspace, self.clock())
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
        ident = uuid.uuid4().hex
        with self.lock:
            self.db.execute("INSERT INTO mandates(id,body,sha256,created) VALUES(?,?,?,?)",
                            (ident, canonical, hashlib.sha256(canonical.encode()).hexdigest(), self.clock()))
        return self.get(ident)

    def _row(self, row):
        body = json.loads(row["body"])
        if hashlib.sha256(row["body"].encode()).hexdigest() != row["sha256"]:
            raise MandateError("Mandate record was modified after it was granted")
        now = self.clock()
        state = "revoked" if row["revoked"] else "expired" if body["expires"] <= now else "active"
        return {"id": row["id"], **body, "state": state, "created": row["created"], "sha256": row["sha256"],
                "used": {"input": row["used_in"], "output": row["used_out"]}}

    def get(self, ident):
        with self.lock:
            row = self.db.execute("SELECT * FROM mandates WHERE id=?", (ident,)).fetchone()
        if row is None:
            raise MandateError("Unknown mandate")
        return self._row(row)

    def active(self):
        with self.lock:
            rows = self.db.execute("SELECT * FROM mandates WHERE revoked IS NULL ORDER BY created DESC LIMIT 20").fetchall()
        return [m for m in (self._row(r) for r in rows) if m["state"] == "active"]

    def revoke(self, ident):
        self.get(ident)
        with self.lock:
            self.db.execute("UPDATE mandates SET revoked=? WHERE id=? AND revoked IS NULL", (self.clock(), ident))
        return self.get(ident)

    def add_usage(self, ident, used_in, used_out):
        with self.lock:
            self.db.execute("UPDATE mandates SET used_in=used_in+?, used_out=used_out+? WHERE id=?",
                            (max(0, int(used_in)), max(0, int(used_out)), ident))

    def remaining(self, ident):
        m = self.get(ident)
        return {"input": m["tokenBudget"]["input"] - m["used"]["input"], "output": m["tokenBudget"]["output"] - m["used"]["output"]}

    # --- run records (the live process is owned by the supervisor) ---
    def run_create(self, mandate_id, session):
        ident = uuid.uuid4().hex
        with self.lock:
            self.db.execute("INSERT INTO runs(id,mandate_id,session,state,started) VALUES(?,?,?,?,?)",
                            (ident, mandate_id, session, "running", self.clock()))
        return ident

    def run_update(self, ident, **fields):
        allowed = {"state", "reason", "ended", "used_in", "used_out", "turns", "pending", "session"}
        if set(fields) - allowed:
            raise MandateError("Unknown run field")
        with self.lock:
            for key, value in fields.items():
                self.db.execute("UPDATE runs SET %s=? WHERE id=?" % key, (value, ident))

    def run_get(self, ident):
        with self.lock:
            row = self.db.execute("SELECT * FROM runs WHERE id=?", (ident,)).fetchone()
        if row is None:
            raise MandateError("Unknown run")
        return dict(row)

    def runs(self, limit=20):
        with self.lock:
            rows = self.db.execute("SELECT * FROM runs ORDER BY started DESC LIMIT ?", (int(limit),)).fetchall()
        return [dict(r) for r in rows]

    def interrupt_orphans(self):
        """Runs left 'running' by a previous process cannot be trusted: mark them interrupted."""
        with self.lock:
            self.db.execute("UPDATE runs SET state='interrupted', reason='service restarted', ended=? "
                            "WHERE state IN ('running','awaiting-approval')", (self.clock(),))
