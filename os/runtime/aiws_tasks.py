"""Persistent AIWS guest task DAG, approvals and integrity-linked audit.

Pure SQLite and Python standard library. Does not invoke a model, subprocess,
host API or privileged operation. The unprivileged guest controller supplies a
separate allowlisted tool runner.
"""
from pathlib import Path
import hashlib
import json
import os
import sqlite3
import threading
import time
from uuid import uuid4
from aiws_guest_ops import TOOLS as GUEST_OP_TOOLS, WRITE_TOOLS as GUEST_OP_WRITES, validate as validate_guest_operation
from aiws_toolplane import catalog as tool_catalog

TOOLS = frozenset({
    "workspace.tree", "file.read", "file.replace", "code.search",
    "git.inspect", "runtime.detect", "browser.local_text", "platform.inspect",
    "code.symbols", "code.references", "code.dependencies", "code.platformApis",
}) | GUEST_OP_TOOLS
WRITE_TOOLS = frozenset({"file.replace"}) | GUEST_OP_WRITES
MAX_STAGES = 32

class TaskError(ValueError):
    pass

def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

class GuestTaskStore:
    def __init__(self, folder, singleton=False):
        self.folder = Path(folder)
        if not self.folder.is_absolute() or self.folder.is_symlink():
            raise TaskError("Guest task state must be an absolute, non-symlink directory")
        self.folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._lock_fd = None
        if singleton:
            # Linux guest only: a second controller must not recover live work.
            import fcntl
            lockpath = self.folder / "controller.lock"
            fd = os.open(lockpath, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                os.close(fd)
                raise TaskError("Guest task controller is already owned") from exc
            self._lock_fd = fd
        if self.folder.is_symlink() or self.folder.stat().st_mode & 0o077:
            raise TaskError("Guest state directory must be mode 0700")
        database = self.folder / "tasks.sqlite3"
        if database.is_symlink():
            raise TaskError("Task database symlinks are forbidden")
        self.lock = threading.RLock()
        self.db = sqlite3.connect(database, timeout=10, isolation_level=None,
                                  check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS tasks(
            id TEXT PRIMARY KEY, title TEXT NOT NULL, goal TEXT NOT NULL,
            created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS stages(
            id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id),
            stage_key TEXT NOT NULL, label TEXT NOT NULL, tool TEXT NOT NULL,
            args_json TEXT NOT NULL, depends_json TEXT NOT NULL,
            state TEXT NOT NULL, approval INTEGER NOT NULL DEFAULT 0,
            error TEXT, result_json TEXT, created_at INTEGER NOT NULL, ordinal INTEGER NOT NULL,
            UNIQUE(task_id,stage_key)
        );
        CREATE TABLE IF NOT EXISTS audit(
            seq INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
            stage_id TEXT, action TEXT NOT NULL, details TEXT NOT NULL,
            previous_hash TEXT NOT NULL, entry_hash TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS task_stages_idx ON stages(task_id,created_at);
        CREATE INDEX IF NOT EXISTS task_audit_idx ON audit(task_id,seq);
        """)
        os.chmod(database, 0o600)
        if not self.verify_audit()["valid"]:
            raise TaskError("Guest audit chain integrity failure")
        self._recover_interrupted()

    def close(self):
        with self.lock:
            self.db.close()
            if self._lock_fd is not None:
                os.close(self._lock_fd)
                self._lock_fd = None

    def verify_audit(self):
        """Check the entire local hash chain; not a guest-root tamper proof."""
        with self.lock:
            previous, count = "GENESIS", 0
            for row in self.db.execute("SELECT * FROM audit ORDER BY seq").fetchall():
                try:
                    details=json.loads(row["details"])
                    payload=encode([row["task_id"],row["stage_id"],row["action"],
                                    details,previous,row["created_at"]])
                    digest=hashlib.sha256(payload.encode("utf-8")).hexdigest()
                except (TypeError, ValueError):
                    return {"valid":False,"events":count,"lastHash":previous}
                if row["previous_hash"] != previous or row["entry_hash"] != digest:
                    return {"valid":False,"events":count,"lastHash":previous}
                previous, count = digest, count + 1
            return {"valid":True,"events":count,"lastHash":previous}

    def _check_audit(self):
        if not self.verify_audit()["valid"]:
            raise TaskError("Guest audit corruption; scheduling blocked")

    def _event(self, task_id, stage_id, action, details):
        timestamp = int(time.time())
        last = self.db.execute("SELECT entry_hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        previous = last["entry_hash"] if last else "GENESIS"
        payload = encode([task_id, stage_id, action, details, previous, timestamp])
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        self.db.execute(
            "INSERT INTO audit(task_id,stage_id,action,details,previous_hash,entry_hash,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (task_id, stage_id, action, encode(details), previous, digest, timestamp))
        return digest

    def _recover_interrupted(self):
        with self.lock:
            rows = self.db.execute(
                "SELECT task_id,id,tool FROM stages WHERE state IN ('queued','running')").fetchall()
            for row in rows:
                self.db.execute(
                    "UPDATE stages SET state='interrupted',approval=?,"
                    "error='Guest restart; explicit review required' WHERE id=?",
                    (0 if row["tool"] in WRITE_TOOLS else 1,row["id"]))
                self._event(row["task_id"], row["id"], "stage.interrupted",
                            {"reason": "guest restart"})

    @staticmethod
    def validate_plan(stages):
        if not isinstance(stages, list) or not (1 <= len(stages) <= MAX_STAGES):
            raise TaskError("Plan requires 1-32 stages")
        keys = []
        for stage in stages:
            if not isinstance(stage, dict) or set(stage) != {
                    "key", "label", "tool", "arguments", "dependsOn"}:
                raise TaskError("Each stage requires key, label, tool, arguments, dependsOn")
            key, label, tool, args, deps = (
                stage["key"], stage["label"], stage["tool"],
                stage["arguments"], stage["dependsOn"])
            if not isinstance(key, str) or not (1 <= len(key) <= 48) or not key.replace("-", "").replace("_", "").isalnum():
                raise TaskError("Invalid stage key")
            if key in keys:
                raise TaskError("Duplicate stage key")
            if not isinstance(label, str) or not (1 <= len(label) <= 160):
                raise TaskError("Stage label required")
            if tool not in TOOLS:
                raise TaskError("Only guest-scoped allowlisted tools may be planned")
            if not isinstance(args, dict) or any(not isinstance(k, str) or
                    not isinstance(v, str) or len(v) > 8192 for k, v in args.items()):
                raise TaskError("Tool arguments must be bounded string values")
            if tool in GUEST_OP_TOOLS:
                validate_guest_operation(tool, args)
            else:
                specs = {x["name"]: x["inputSchema"] for x in tool_catalog()}
                schema = specs.get(tool)
                if not schema or set(args) - set(schema["properties"]) or any(
                        field not in args for field in schema["required"]):
                    raise TaskError("Missing/unknown tool arguments")
            if not isinstance(deps, list) or len(deps) > MAX_STAGES or any(not isinstance(x, str) for x in deps):
                raise TaskError("Invalid dependencies")
            keys.append(key)
        adjacency = {x["key"]: x["dependsOn"] for x in stages}
        for key, deps in adjacency.items():
            if len(set(deps)) != len(deps) or key in deps or any(d not in adjacency for d in deps):
                raise TaskError("Dependency references invalid")
        seen = set()
        def visit(key, active):
            if key in active:
                raise TaskError("DAG contains a cycle")
            if key in seen:
                return
            for dep in adjacency[key]:
                visit(dep, active | {key})
            seen.add(key)
        for key in keys:
            visit(key, set())

    def create(self, title, goal, stages):
        if not isinstance(title, str) or not (1 <= len(title) <= 160):
            raise TaskError("Task title required")
        if not isinstance(goal, str) or len(goal) > 4000:
            raise TaskError("Task goal too long")
        self.validate_plan(stages)
        identifier, now = uuid4().hex, int(time.time())
        with self.lock:
            self._check_audit()
            self.db.execute("BEGIN IMMEDIATE")
            try:
                self.db.execute(
                    "INSERT INTO tasks(id,title,goal,created_at,updated_at) VALUES(?,?,?,?,?)",
                    (identifier, title, goal, now, now))
                for ordinal, stage in enumerate(stages):
                    approval = int(stage["tool"] not in WRITE_TOOLS)
                    self.db.execute(
                        "INSERT INTO stages(id,task_id,stage_key,label,tool,args_json,"
                        "depends_json,state,approval,created_at,ordinal) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (uuid4().hex, identifier, stage["key"], stage["label"],
                         stage["tool"], encode(stage["arguments"]), encode(stage["dependsOn"]),
                         "pending", approval, now, ordinal))
                self._event(identifier, None, "task.created",
                            {"title": title, "stages": [
                                {"key": s["key"], "tool": s["tool"],
                                 "dependsOn": s["dependsOn"], "argsSha256":
                                  hashlib.sha256(encode(s["arguments"]).encode("utf-8")).hexdigest()}
                                for s in stages]})
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise
        return self.get(identifier)

    def list(self):
        with self.lock:
            return [dict(x) for x in self.db.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC,id DESC LIMIT 100").fetchall()]

    def get(self, task_id):
        with self.lock:
            task = self.db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if not task:
                raise TaskError("Unknown task ID")
            stages = self.db.execute(
                "SELECT * FROM stages WHERE task_id=? ORDER BY ordinal",
                (task_id,)).fetchall()
            values = []
            for row in stages:
                item = dict(row)
                item["arguments"] = json.loads(item.pop("args_json"))
                item["dependsOn"] = json.loads(item.pop("depends_json"))
                if item["result_json"] is not None:
                    item["result"] = json.loads(item.pop("result_json"))
                else:
                    item.pop("result_json")
                    item["result"] = None
                values.append(item)
            return {"task": dict(task), "stages": values}

    def record_model_proposal(self, task_id, model_name, prompt, proposal):
        """Link a model proposal to a durable task without storing the prompt."""
        if not isinstance(prompt, str) or not isinstance(proposal, dict):
            raise TaskError("Invalid model provenance")
        self.get(task_id)
        with self.lock:
            self._check_audit()
            self._event(task_id, None, "model.proposed",
                        {"model": model_name,
                         "promptSha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                         "proposalSha256": hashlib.sha256(encode(proposal).encode("utf-8")).hexdigest(),
                         "autoExecuted": False,
                         "reviewRequired": True})

    def audit(self, task_id):
        self.get(task_id)
        with self.lock:
            rows = self.db.execute(
                "SELECT * FROM audit WHERE task_id=? ORDER BY seq", (task_id,)).fetchall()
            return [dict(row) for row in rows]

    def _row(self, task_id, stage_key):
        row = self.db.execute(
            "SELECT * FROM stages WHERE task_id=? AND stage_key=?",
            (task_id, stage_key)).fetchone()
        if not row:
            raise TaskError("Unknown stage")
        return row

    def approve(self, task_id, stage_key):
        with self.lock:
            self._check_audit()
            row = self._row(task_id, stage_key)
            if row["state"] not in ("pending", "interrupted") or row["tool"] not in WRITE_TOOLS:
                raise TaskError("Only pending guest-write stages require approval")
            self.db.execute("UPDATE stages SET approval=1 WHERE id=?", (row["id"],))
            self._event(task_id, row["id"], "stage.approved",
                        {"tool": row["tool"], "guest_only": True})
            return self.get(task_id)

    def dispatch(self, task_id, stage_key):
        with self.lock:
            self._check_audit()
            row = self._row(task_id, stage_key)
            if row["state"] not in ("pending", "interrupted"):
                raise TaskError("Stage already queued/running/completed; cannot double dispatch")
            if not row["approval"]:
                raise TaskError("Guest-write stage requires explicit approval")
            dependencies = json.loads(row["depends_json"])
            for dep in dependencies:
                state = self._row(task_id, dep)["state"]
                if state != "completed":
                    raise TaskError("Prerequisite has not completed: " + dep)
            self.db.execute("UPDATE stages SET state='queued',error=NULL WHERE id=?", (row["id"],))
            self._event(task_id, row["id"], "stage.queued", {"key": stage_key})
            return {"id": row["id"], "task_id": task_id, "stage_key": stage_key,
                    "tool": row["tool"], "arguments": json.loads(row["args_json"]),
                    "approvalGranted": bool(row["approval"])}

    def started(self, task_id, stage_key):
        with self.lock:
            self._check_audit()
            row = self._row(task_id, stage_key)
            if row["state"] != "queued":
                raise TaskError("Expected queued stage")
            self.db.execute("UPDATE stages SET state='running' WHERE id=?", (row["id"],))
            self._event(task_id, row["id"], "stage.running", {"key": stage_key})

    def finished(self, task_id, stage_key, result=None, error=None):
        with self.lock:
            self._check_audit()
            row = self._row(task_id, stage_key)
            if row["state"] != "running":
                raise TaskError("Expected running stage")
            state = "failed" if error else "completed"
            # Audit only evidence metadata, not arbitrary workspace file contents.
            digest = hashlib.sha256(encode(result).encode("utf-8")).hexdigest() if result is not None else None
            self.db.execute(
                "UPDATE stages SET state=?,result_json=?,error=? WHERE id=?",
                (state, encode(result)[:65536] if result is not None else None,
                 str(error)[:240] if error else None, row["id"]))
            self._event(task_id, row["id"], "stage." + state,
                        {"result_sha256": digest, "error": str(error)[:240] if error else None})
            return self.get(task_id)
