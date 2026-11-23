"""The assistant service: what the workbench talks to. It owns the local agent, its threads, skills, plugins and the router statistics.

The workbench stays thin: it checks the request (CSRF, shape), calls one method here and returns the result. Everything with state
or a rule lives in this file and is tested without a browser.

A turn can take minutes on a CPU, so it runs in a background thread and the page follows it by reading the thread: every item is
written to disk the moment it exists (aiws_local_agent.ThreadStore), so "live progress" is just reading the file again.
The workbench passes in four things so this module needs no knowledge of its internals:
  invoke(name, args)      runs a READ tool (embedded, or through the Agent service)
  persist(text, proposal) turns a validated proposal into a task with approvals (the same path the one-shot planner uses)
  emit(event)             observatory events (optional)
  enabled()               whether the person has switched the local model on
"""
import json
import threading
import time
from pathlib import Path

import aiws_llm
import aiws_local_agent as A
import aiws_plugins
import aiws_route
import aiws_skills
from aiws_local_model import READ_TOOLS as MODEL_READ_TOOLS

HOST_URL = "http://127.0.0.1:18080"
UI_HIDE = ("prompt",)                         # large and already visible as `text` + `tools`; the UI does not need it
UI_MAX_ITEMS = 300
TIERS_FOR_OVERRIDE = aiws_route.TIERS


class Assistant:
    def __init__(self, state_dir, invoke, catalog, persist, emit=None, enabled=None, skills_dir=None, pinned=None, system_plugins_dir=aiws_plugins.SYSTEM_DIR,
                 llm=None, read_tools=MODEL_READ_TOOLS):
        base = Path(state_dir) / "assistant"
        self.port = A.PlanePort(invoke, catalog, read_tools)
        # The product endpoint is the model gate (or the host channel): neither streams, and a CPU step can take minutes, hence no streaming and 10 minutes.
        self.llm = llm or aiws_llm.LocalLLM(HOST_URL, timeout=600, features={"stream": False})
        self.plugins = aiws_plugins.PluginManager(base / "plugins", base / "plugins-state.json", system_plugins_dir, self.port.names())
        self.skills = aiws_skills.SkillBook(skills_dir, pinned if pinned is not None else {}, self.plugins, self.port.names())
        self.store = A.ThreadStore(base / "threads")
        self.stats = aiws_route.RouteStats(base / "route.json")
        self.agent = A.LocalAgent(self.llm, self.port, self.store, skills=self.skills, plugins=self.plugins, emit=self._observe)
        self._persist, self._emit, self._enabled = persist, emit, enabled or (lambda: True)
        self._running = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ observatory
    def _observe(self, event):
        if self._emit is not None:
            try:
                self._emit(event)
            except Exception:                      # observability must never break a turn
                pass

    # ------------------------------------------------------------------ status
    def status(self):
        probe = self.llm.probe() if self._enabled() else {"state": "off", "ctx": None, "server": None, "model": None}
        return {"enabled": bool(self._enabled()), "model": probe, "busy": A.RUN_LOCK.locked(), "tools": self.port.names(),
                "skills": [{"id": i, "description": d, "source": s} for i, d, s in self.skills.catalog()], "skillProblems": [list(p) for p in self.skills.problems][:20],
                "commands": [{"id": c["id"], "description": c["description"], "argumentHint": c["argumentHint"]} for c in self.plugins.active_commands().values()],
                "plugins": {"total": len(self.plugins.plugins), "enabled": sum(1 for p in self.plugins.plugins.values() if p["status"] == "enabled")},
                "route": self.stats.get(), "limits": {k: A.LIMITS[k] for k in ("maxSteps", "maxCalls", "maxSeconds", "maxTextChars")}}

    # ------------------------------------------------------------------ routing
    def route(self, text):
        decision = aiws_route.decide(text, self.llm if self._enabled() else None, self.plugins.active_floors())
        self.stats.record(decision)
        return decision

    def route_override(self, from_tier, to_tier):
        self.stats.override(from_tier, to_tier)
        return self.stats.get()

    # ------------------------------------------------------------------ threads
    def threads(self):
        return {"threads": self.store.list(30)}

    def thread(self, thread_id):
        items = self.store.load(thread_id)
        view = [{k: v for k, v in it.items() if k not in UI_HIDE} for it in items[-UI_MAX_ITEMS:]]
        with self._lock:
            running = thread_id in self._running
        return {"id": thread_id, "items": view, "running": running, "truncated": len(items) > UI_MAX_ITEMS}

    # ------------------------------------------------------------------ a turn, in the background
    def start_turn(self, text, thread_id=None, route=None):
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= A.LIMITS["maxTextChars"]:
            raise A.AgentError("bad_request", "The request must be 1-%d characters" % A.LIMITS["maxTextChars"])
        if not self._enabled():
            raise A.AgentError("unavailable", "The local model is switched off. Turn it on in the System page first.")
        if A.RUN_LOCK.locked():
            raise A.AgentError("busy", "The local model is working on another request")
        if thread_id is None:
            thread_id = self.store.create()
        elif not self.store.exists(thread_id):
            raise A.AgentError("bad_request", "No such thread")
        with self._lock:
            if thread_id in self._running:
                raise A.AgentError("busy", "This thread is already running")
            self._running[thread_id] = time.time()
        threading.Thread(target=self._run, args=(thread_id, text.strip(), route if isinstance(route, str) else None), daemon=True).start()
        return {"threadId": thread_id, "started": True}

    def _note(self, thread_id, item):
        try:
            self.store.append(thread_id, self.store.load(thread_id), item)
        except (A.AgentError, OSError):
            pass

    def _run(self, thread_id, text, route_tier):
        try:
            result = self.agent.run_turn(thread_id, text, route=route_tier)
            if route_tier == "local":
                self.stats.completed_locally(result["outcome"])
            if result["outcome"] == "proposed":
                try:
                    doc = self._persist(text, result["proposal"])
                    task = (doc or {}).get("task") or {}
                    self._note(thread_id, {"type": "plan", "taskId": task.get("id"), "title": str(task.get("title") or "")[:160]})
                except Exception as exc:                    # the proposal is already in the thread; say why no plan was made
                    self._note(thread_id, {"type": "error", "outcome": "error", "error": "plan", "text": "Could not create the plan: %s" % str(exc)[:160]})
        except A.AgentError as exc:
            self._note(thread_id, {"type": "error", "outcome": "error", "error": exc.kind, "text": str(exc)[:200]})
        except Exception as exc:                            # never let a thread die silently
            self._note(thread_id, {"type": "error", "outcome": "error", "error": "internal", "text": "Unexpected error: %s" % type(exc).__name__})
        finally:
            with self._lock:
                self._running.pop(thread_id, None)

    # ------------------------------------------------------------------ plugins
    def plugin_list(self):
        self.plugins.scan()
        self.skills.refresh()
        return {"plugins": self.plugins.list(), "problems": [list(p) for p in self.plugins.problems][:20]}

    def plugin_enable(self, name, tree_sha256=None):
        try:
            status = self.plugins.enable(name, tree_sha256)
        except aiws_plugins.PluginError as exc:
            raise ValueError(str(exc))
        self.skills.refresh()
        return {"name": name, "status": status}

    def plugin_disable(self, name):
        try:
            status = self.plugins.disable(name)
        except aiws_plugins.PluginError as exc:
            raise ValueError(str(exc))
        self.skills.refresh()
        return {"name": name, "status": status}

    # ------------------------------------------------------------------ after a restart
    def recover(self, limit=5):
        """Finish reads that were committed but not answered when the process stopped. Safe: they are read-only and idempotent."""
        done = 0
        for t in self.store.list(limit):
            try:
                if self.agent.recover(t["id"]):
                    done += 1
            except Exception:
                continue
        return done


def observatory_events(event):
    """Map an agent event to observatory fields: (kind, fields) or None. The workbench passes the result to its own emitter."""
    kind = event.get("kind")
    if kind == "start":
        return "start", {"detail": "assistant turn"}
    if kind == "tool":
        status = {"ok": "ok", "error": "error", "blocked": "denied"}.get(event.get("status"), "unknown")
        tool = event.get("tool") or "unknown"
        return "tool", {"tool": tool if aiws_events_safe(tool) else "unknown", "status": status}
    if kind == "skill":
        return "message", {"detail": ("skill " + str(event.get("skill")))[:60]}
    if kind == "end":
        m = event.get("metrics") or {}
        usage = m.get("usage") or {}
        counts = {"in": usage.get("promptTokens"), "out": usage.get("completionTokens"), "cacheRead": usage.get("cacheN") if usage.get("cacheN") is not None else usage.get("cachedTokens")}
        tokens = ({**counts, "cacheWrite": None, "source": "reported", "scope": "turn"} if any(v is not None for v in counts.values())
                  else {"source": "unknown", "scope": "turn"})
        prog = {"tools": int(m.get("calls") or 0), "ms": int(m.get("doneMs") or 0)}
        return "end", {"detail": str(event.get("outcome") or "")[:60], "tokens": tokens, "prog": prog}
    return None


def aiws_events_safe(name):
    import aiws_events
    return isinstance(name, str) and bool(aiws_events.SAFE_NAME.match(name))
