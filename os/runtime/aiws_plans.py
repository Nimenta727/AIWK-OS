"""Structured plans for the review panel. Pure functions plus a small bounded store; nothing here executes anything.

Two sources, one shape:
  local   the local planner's task stages (already structured: tool, arguments, dependencies, approval state).
  cloud   what an official CLI announced: TodoWrite todos (structured) or an ExitPlanMode plan (free text).

The shape is {id, source, title, status, steps:[{id, title, detail, tool, targets, risk, deps, state, parsed}]}.
RISK IS COMPUTED HERE from the tool class and its targets, never taken from the model's own claim. For cloud text plans
the tools are unknown, so risk is "unknown" plus *keyword hints* (delete, push, install ...) shown as hints, not verdicts.
Free text is turned into steps by a plain list parser and every such plan is marked `parsed: "text"` (may be inexact).
"""
import json
import re
import time
from pathlib import Path

import aiws_toolplane as tp
from aiws_events import CONTROL, redact

MAX_STEPS = 40
MAX_PLANS = 100
MAX_TEXT = 20000
HINTS = (("delete", r"\b(delete|remove|rm\b|drop|truncate|wipe|erase|删除|清空)"), ("push", r"\bgit\s+push|force[- ]push|推送"),
         ("install", r"\b(install|npm i\b|pip install|apt(-get)?\s+install|安装)"), ("network", r"\b(curl|wget|http[s]?://|download|下载|联网)"),
         ("privilege", r"\b(sudo|chmod|chown|root)\b|提权"), ("secrets", r"(?i)(\.env\b|api[_ -]?key|token|password|密钥)"))
BULLET = re.compile(r"^(\s*)(?:(\d{1,2})[.)、]|[-*•]|\[[ xX]\])\s+(.*\S)\s*$")


def risk_of(tool, args=None):
    """low (reads) < medium (workspace writes) < high (deletes, program launches, service/kernel operations)."""
    if tool in tp.READ_TOOLS:
        return "low"
    if tool in ("file.trash", "file.restore"):
        return "high"
    if tool in tp.FILE_WRITE_TOOLS:
        return "medium"
    if tool in tp.APP_LAUNCH_TOOLS:
        return "high"
    if tool.startswith(("service.", "kernel.")):
        return "low" if tool.endswith(("inspect", "verify", "recovery_plan")) else "high"
    return "high"                                          # unknown tool class: assume the worst, never the best


def hints_of(text):
    return [name for name, rx in HINTS if re.search(rx, text, re.I)]


def _clean(text, limit):
    return CONTROL.sub(" ", str(text)).strip()[:limit]


def from_local(task, stages):
    steps = []
    for s in stages:
        args = s.get("arguments") or {}
        targets = [v for k, v in args.items() if k in ("path", "source", "destination", "target", "query") and isinstance(v, str)][:3]
        steps.append({"id": s["stage_key"], "title": _clean(s.get("label", ""), 160), "detail": None, "tool": s.get("tool"),
                      "targets": [_clean(t, 120) for t in targets], "risk": risk_of(s.get("tool", ""), args),
                      "deps": list(s.get("dependsOn") or []), "state": s.get("state", "pending"),
                      "needsApproval": bool(s.get("approval") == 0 and s.get("state") in ("pending", "interrupted")), "parsed": None})
    state = {x["state"] for x in steps}
    status = ("failed" if "failed" in state else "running" if "running" in state else
              "done" if state == {"completed"} else "awaiting-approval" if any(x["needsApproval"] for x in steps) else "proposed")
    return {"id": task["id"], "source": "local", "title": _clean(task.get("title", ""), 120), "goal": _clean(task.get("goal", ""), 300),
            "status": status, "steps": steps, "createdAt": task.get("created_at")}


def from_todos(todos):
    """TodoWrite input: [{content, status, activeForm}]. Structured, so no parsing guesswork."""
    steps = []
    for i, t in enumerate(todos if isinstance(todos, list) else []):
        if not isinstance(t, dict) or not isinstance(t.get("content"), str):
            continue
        title = _clean(redact(t["content"], 160), 160)
        st = {"pending": "pending", "in_progress": "running", "completed": "completed"}.get(t.get("status"), "pending")
        steps.append({"id": "t%d" % (i + 1), "title": title, "detail": None, "tool": None, "targets": [], "risk": "unknown",
                      "hints": hints_of(title), "deps": [], "state": st, "needsApproval": False, "parsed": None})
        if len(steps) >= MAX_STEPS:
            break
    return steps


def parse_text(text):
    """A plain list parser: numbered or bulleted lines are steps, deeper-indented lines become the previous step's detail,
    prose before the first list item becomes the goal. Anything else is ignored. Deterministic; no model."""
    text = str(text)[:MAX_TEXT]
    steps, goal, cur, base = [], [], None, None
    for raw in text.splitlines():
        m = BULLET.match(raw.replace("\t", "    "))
        if m:
            indent = len(m.group(1))
            if base is None:
                base = indent
            if indent <= base + 1 or cur is None:
                if len(steps) >= MAX_STEPS:
                    break
                cur = {"id": "s%d" % (len(steps) + 1), "title": _clean(redact(re.sub(r"^\*\*(.*?)\*\*", r"\1", m.group(3)), 200), 200), "detail": [],
                       "tool": None, "targets": [], "risk": "unknown", "deps": [], "state": "pending", "needsApproval": False, "parsed": "text"}
                steps.append(cur)
            else:
                cur["detail"].append(_clean(redact(m.group(3), 200), 200))
        elif raw.strip() and cur is None and not raw.lstrip().startswith("#"):
            goal.append(_clean(raw, 200))
    for s in steps:
        s["detail"] = " · ".join(s["detail"][:6]) or None
        s["hints"] = hints_of(s["title"] + " " + (s["detail"] or ""))
    return " ".join(goal)[:300], steps


def from_native(run_id, plan):
    """A plan proposed by our own runner: structured, so risk is computed from each step's tool, like a local plan."""
    steps = []
    for i, st in enumerate(plan.get("steps") or [], 1):
        tool = st.get("tool") if isinstance(st.get("tool"), str) else None
        title = _clean(redact(st.get("title", ""), 160), 160)
        steps.append({"id": "n%d" % i, "title": title, "detail": None, "tool": tool, "targets": [_clean(t, 120) for t in (st.get("targets") or [])][:3],
                      "risk": risk_of(tool) if tool else "unknown", "hints": hints_of(title), "deps": ["n%d" % d for d in (st.get("deps") or []) if isinstance(d, int) and 1 <= d < i],
                      "state": "pending", "needsApproval": False, "parsed": None})
    seq = plan.get("seq") if isinstance(plan.get("seq"), int) else 1
    return {"id": "cloud-" + re.sub(r"[^A-Za-z0-9_-]", "_", str(run_id))[:48] + "-native-%d" % seq, "source": "cloud", "kind": "native", "runId": str(run_id)[:64], "seq": seq,
            "title": _clean(plan.get("title", ""), 120) or "DeepSeek plan", "goal": _clean(plan.get("goal", ""), 300), "status": "proposed",
            "steps": steps[:MAX_STEPS], "createdAt": time.time(), "parsedFromText": False}


def from_cloud(run_id, kind, payload):
    """kind 'todo', 'text' or 'native'. Returns a plan in the common shape."""
    if kind == "native":
        return from_native(run_id, payload)
    if kind == "todo":
        steps, goal = from_todos(payload), ""
    else:
        goal, steps = parse_text(payload)
    done = bool(steps) and all(s["state"] == "completed" for s in steps)
    return {"id": "cloud-" + re.sub(r"[^A-Za-z0-9_-]", "_", str(run_id))[:48] + "-" + kind, "source": "cloud", "kind": kind,
            "title": "Claude Code · " + ("todo list" if kind == "todo" else "plan"), "goal": goal,
            "status": "done" if done else ("running" if any(s["state"] == "running" for s in steps) else "proposed"),
            "steps": steps, "createdAt": time.time(), "parsedFromText": kind == "text"}


class PlanStore:
    """Cloud plans only (local ones live in the task store). One JSON file, atomic replace, bounded, private."""

    def __init__(self, path):
        self.path = Path(path)

    def _read(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def upsert(self, plan):
        data = self._read()
        data[plan["id"]] = plan
        if len(data) > MAX_PLANS:                              # drop the oldest
            for k in sorted(data, key=lambda k: data[k].get("createdAt") or 0)[:len(data) - MAX_PLANS]:
                data.pop(k)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.chmod(0o600)
        tmp.replace(self.path)

    def list(self):
        return sorted(self._read().values(), key=lambda p: p.get("createdAt") or 0, reverse=True)

    def _modify(self, plan_id, fn):
        data = self._read()
        if plan_id not in data:
            return False
        fn(data[plan_id])
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.chmod(0o600)
        tmp.replace(self.path)
        return True

    def set_status(self, plan_id, status):
        return self._modify(plan_id, lambda p: p.__setitem__("status", status))

    def update_step(self, plan_id, step, state):
        """step is 1-based. Marks the plan done when every step is completed, running while any is."""
        def fn(p):
            if isinstance(step, int) and 1 <= step <= len(p["steps"]) and state in ("running", "completed", "failed"):
                p["steps"][step - 1]["state"] = state
            states = {s["state"] for s in p["steps"]}
            if states == {"completed"}:
                p["status"] = "done"
            elif "failed" in states:
                p["status"] = "failed"
            elif "running" in states or "completed" in states:
                p["status"] = "running"
        return self._modify(plan_id, fn)


class ResultStore:
    """The final answer of each run (bounded, private). Event store never holds message text, so the answer lives here."""
    MAX = 30

    def __init__(self, path):
        self.path = Path(path)

    def _read(self):
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def put(self, run_id, text):
        data = self._read()
        data[str(run_id)[:64]] = {"text": str(text)[:20000], "ts": time.time()}
        for k in sorted(data, key=lambda k: data[k]["ts"])[:max(0, len(data) - self.MAX)]:
            data.pop(k)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.chmod(0o600)
        tmp.replace(self.path)

    def last(self):
        data = self._read()
        if not data:
            return None
        k = max(data, key=lambda k: data[k]["ts"])
        return {"runId": k, **data[k]}
