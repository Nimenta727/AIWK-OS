"""HTTP layer of the guest workbench: request checks, the route table, responses.

Security entry point. Rules every request goes through, in this order:
  GET : Host must be exactly 127.0.0.1:<port> (DNS rebinding) -> route table -> static UI assets -> 404
  POST: Host -> the path must be in POST_ROUTES (else 404, before anything else is looked at) -> Origin (if sent)
        must be this service -> X-AIWS-CSRF must match (constant time) -> Content-Type application/json ->
        0 < Content-Length <= 16 KiB -> body must be a JSON object -> the route's own field checks
A path that is not in the tables below is never served. test_workbench_routes.py holds the tables to that.

Path patterns are split on "/". A segment written {name} matches any one non-empty segment and is passed to the
handler as params[name]; the application layer validates the value. Every other segment must match literally.
"""
from http.server import BaseHTTPRequestHandler
import json
import secrets
from urllib.parse import parse_qs, urlsplit

import aiws_agent_tree
import aiws_apps
import aiws_capabilities
import aiws_changes
import aiws_plans
import aiws_route
import aiws_secrets
from aiws_agent_client import AgentUnavailable, AgentError
from aiws_events import SAFE_NAME
from aiws_guest_ops import catalog as guest_catalog
from aiws_local_agent import AgentError as LocalAgentError
from aiws_model_router import RouterError
from aiws_supervisor import SupervisorError
from aiws_tasks import TaskError
from aiws_toolplane import audit, catalog, invoke, READ_TOOLS, _path as workspace_path, _workspace

HOST = "127.0.0.1"
EXPOSED = READ_TOOLS           # /jobs runs read tools only; guest writes go through approved durable DAG stages
MAX_BODY = 16384
ASSETS = {".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml",
          ".png": "image/png", ".jpg": "image/jpeg", ".ico": "image/x-icon",
          ".woff2": "font/woff2", ".woff": "font/woff", ".ttf": "font/ttf"}   # .ttf: the codicon icon font
GUEST_SERVICES = ("aiws-workbench.service", "aiws-agent.service",
                  "aiws-permission-broker.service", "aiws-local-model.service")


# ------------------------------------------------------------------------------------------------ route matching
def _segments(path):
    # only the one leading "/" is dropped: "/api/v1/tasks/" has an empty last segment and matches nothing
    return path[1:].split("/") if path.startswith("/") else [None]


def _compile(table):
    return [(tuple(_segments(pattern)), fn) for pattern, fn in table]


def match(routes, path):
    """(handler, params) for the first pattern that matches path exactly, else (None, None)."""
    parts = _segments(path)
    for segments, fn in routes:
        if len(segments) != len(parts):
            continue
        params = {}
        for want, got in zip(segments, parts):
            if want.startswith("{") and want.endswith("}"):
                if not got:
                    break
                params[want[1:-1]] = got
            elif want != got or got is None:
                break
        else:
            return fn, params
    return None, None


def _one(q, key):
    """Exactly one bounded value for key, else ValueError (-> 400)."""
    values = q.get(key, [])
    if len(values) != 1 or not values[0] or len(values[0]) > 512:
        raise ValueError("One bounded guest-workspace path required")
    return values[0]


def _err(exc, limit=240):
    return {"error": str(exc)[:limit]}


# --------------------------------------------------------------------------------------------------- GET routes
# Each handler is fn(h, app, q, p): h is the request handler, q the parsed query string, p the path params.
def _plane_read(h, app, tool, args):
    """A read tool through the agent service when there is one, else in process (then audited here)."""
    try:
        result = app.file_tools.invoke(tool, args) if app.file_tools is not None else invoke(tool, args)
        if app.file_tools is None:
            audit(tool, args, True)
        return h.reply(200, result)
    except AgentUnavailable as exc:
        return h.reply(503, _err(exc))
    except (ValueError, OSError, PermissionError) as exc:
        return h.reply(403, _err(exc))


def _with_path(tool):
    def get(h, app, q, p):
        try:
            path = _one(q, "path")
        except ValueError as exc:
            return h.reply(400, _err(exc))
        return _plane_read(h, app, tool, {"path": path})
    return get


def _agent(h, call):
    try:
        return h.reply(200, call())
    except (AgentUnavailable, AgentError) as exc:
        return h.reply(503, _err(exc))


def _task_call(h, call):
    try:
        return h.reply(200, call())
    except TaskError as exc:
        return h.reply(404, {"error": str(exc)})
    except (AgentUnavailable, AgentError) as exc:
        return h.reply(503, _err(exc))


def _guest_op(h, call):
    try:
        return h.reply(200, call())
    except (PermissionError, ValueError, OSError) as exc:
        return h.reply(403, _err(exc))


def get_observatory_events(h, app, q, p):
    session = (q.get("session") or [""])[0]
    try:
        after = int((q.get("after") or ["0"])[0])
    except ValueError:
        return h.reply(400, {"error": "after must be an integer"})
    if not SAFE_NAME.match(session) or after < 0:
        return h.reply(400, {"error": "A valid session id is required"})
    return h.reply(200, {"session": session, "events": app.events.events(session, after=after, limit=200)})


def get_observatory_tree(h, app, q, p):
    session = (q.get("session") or [""])[0]
    if not SAFE_NAME.match(session):
        return h.reply(400, {"error": "A valid session id is required"})
    events, after = [], 0
    while len(events) < 5000:                      # bounded: the tree never needs more than this
        page = app.events.events(session, after=after, limit=500)
        if not page:
            break
        events += page
        after = page[-1]["seq"]
    return h.reply(200, {"session": session, **aiws_agent_tree.build(events)})


def get_plans(h, app, q, p):
    plans = list(app.plans.list())[:30]
    try:
        for row in (app.tasks.overview().get("recent") or [])[:8]:
            detail = app.tasks.get(row["id"])
            plans.append(aiws_plans.from_local(detail["task"], detail["stages"]))
    except (TaskError, AgentUnavailable, AgentError):
        pass
    return h.reply(200, {"plans": plans})


def get_capabilities(h, app, q, p):
    query = (q.get("q") or [""])[0][:300]
    try:
        k = int((q.get("k") or ["6"])[0])
        kinds = [x for x in (q.get("kind") or [""])[0].split(",") if x] or None
        hits = app.capabilities.select(query, k, kinds) if query else []
    except (ValueError, aiws_capabilities.CapabilityError) as exc:
        return h.reply(400, _err(exc, 120))
    return h.reply(200, {"hits": hits, "counts": app.capabilities.counts()})


def get_assistant_thread(h, app, q, p):
    ident = (q.get("id") or [""])[0]
    try:
        return h.reply(200, app.assistant.thread(ident))
    except LocalAgentError as exc:
        return h.reply(404 if "No such" in str(exc) else 400, _err(exc, 160))


def _changes(diff):
    def get(h, app, q, p):
        try:
            if diff:
                return h.reply(200, aiws_changes.diff(app.workspace, (q.get("path") or ["."])[0], (q.get("file") or [""])[0]))
            return h.reply(200, aiws_changes.changes(app.workspace, (q.get("path") or ["."])[0]))
        except aiws_changes.ChangesError as exc:
            return h.reply(400, {"error": str(exc)})
    return get


def get_workspace_raw(h, app, q, p):
    try:
        path = _one(q, "path")
    except ValueError as exc:
        return h.reply(400, _err(exc))
    return h.reply_raw(path)


def get_route_config(h, app, q, p):
    try:
        config = app.route_config()
    except RouterError as exc:
        return h.reply(403, _err(exc))
    return h.reply(200, {"config": config, "file": "~/.config/aiws/routes.json", "editableInUi": False})


def get_job(h, app, q, p):
    job = app.job(p["id"])
    return h.reply(200, job) if job else h.reply(404, {"error": "Unknown job"})


GET_ROUTES = _compile([
    ("/api/v1/workspace/tree", lambda h, app, q, p: _plane_read(h, app, "workspace.tree", {"path": "."})),
    ("/api/v1/workspace/stat", _with_path("file.stat")),
    ("/api/v1/workspace/trash", lambda h, app, q, p: _plane_read(h, app, "file.trashList", {})),
    ("/api/v1/workspace/file", _with_path("file.read")),
    ("/api/v1/workspace/doc", _with_path("doc.text")),
    ("/api/v1/workspace/raw", get_workspace_raw),
    ("/api/v1/audit/verify", lambda h, app, q, p: _agent(h, app.tasks.verify_audit)),
    ("/api/v1/tasks", lambda h, app, q, p: _agent(h, lambda: {"tasks": app.tasks.list()})),
    ("/api/v1/tasks/{task}", lambda h, app, q, p: _task_call(h, lambda: app.tasks.get(p["task"]))),
    ("/api/v1/tasks/{task}/audit", lambda h, app, q, p: _task_call(h, lambda: {"events": app.tasks.audit(p["task"])})),
    ("/api/v1/guest/services", lambda h, app, q, p: _guest_op(h, lambda: {"services": [
        app.guest_ops.execute("service.inspect", {"service": name}) for name in GUEST_SERVICES]})),
    ("/api/v1/guest/kernel", lambda h, app, q, p: _guest_op(h, lambda: app.guest_ops.execute("kernel.inspect", {}))),
    ("/api/v1/observatory", lambda h, app, q, p: _agent(h, app.observatory)),
    ("/api/v1/observatory/events", get_observatory_events),
    ("/api/v1/observatory/tree", get_observatory_tree),
    ("/api/v1/plans", get_plans),
    ("/api/v1/capabilities", get_capabilities),
    ("/api/v1/assistant/status", lambda h, app, q, p: h.reply(200, app.assistant.status())),
    ("/api/v1/assistant/threads", lambda h, app, q, p: h.reply(200, app.assistant.threads())),
    ("/api/v1/assistant/thread", get_assistant_thread),
    ("/api/v1/assistant/plugins", lambda h, app, q, p: h.reply(200, app.assistant.plugin_list())),
    ("/api/v1/memory", lambda h, app, q, p: h.reply(200, {"memory": app.memory.list()})),
    ("/api/v1/cloud/key", lambda h, app, q, p: h.reply(200, aiws_secrets.status())),
    ("/api/v1/preview", lambda h, app, q, p: h.reply(200, app.preview.status())),
    ("/api/v1/changes", _changes(diff=False)),
    ("/api/v1/changes/diff", _changes(diff=True)),
    ("/api/v1/system", lambda h, app, q, p: h.reply(200, app.system.status())),
    ("/api/v1/ide", lambda h, app, q, p: h.reply(200, app.ide_status())),
    ("/api/v1/apps", lambda h, app, q, p: h.reply(200, {"apps": aiws_apps.listing()})),
    ("/api/v1/builder", lambda h, app, q, p: h.reply(200, app.builder_overview())),
    ("/api/v1/route/config", get_route_config),
    ("/api/v1/model/status", lambda h, app, q, p: h.reply(200, app.model.status())),
    ("/api/v1/health", lambda h, app, q, p: h.reply(200, app.health())),
    ("/api/v1/session", lambda h, app, q, p: h.reply(200, {"csrf": app.csrf, "mode": "linux-guest"})),
    ("/api/v1/snapshot", lambda h, app, q, p: h.reply(200, {
        "health": app.health(), "jobs": app.recent(),
        "capabilities": [x for x in catalog() if x["name"] in EXPOSED] + guest_catalog()})),
    ("/api/v1/jobs/{id}", get_job),
])


# -------------------------------------------------------------------------------------------------- POST routes
# Each handler is fn(app, payload, p) -> result (sent as 202). Raising maps to a status in Handler.do_POST.
def _empty(payload, message="No arguments allowed"):
    if payload:
        raise ValueError(message)


def _exactly(payload, keys, message):
    if set(payload) != set(keys):
        raise ValueError(message)


def post_jobs(app, payload, p):
    _exactly(payload, {"tool", "arguments"}, "Expected tool and arguments")
    return app.submit(payload["tool"], payload["arguments"])


def post_model_toggle(enabled):
    def post(app, payload, p):
        _empty(payload, "Model toggle accepts no body fields")
        return app.configure_model(enabled)
    return post


def post_apps_launch(app, payload, p):
    _exactly(payload, {"id"}, "Expected the application id only")
    return app.apps_launch(payload["id"])


def post_assistant_turn(app, payload, p):
    if not {"text"} <= set(payload) <= {"text", "threadId", "tier"} or not isinstance(payload["text"], str):
        raise ValueError("Expected text, optionally threadId and tier")
    tier = payload.get("tier")
    if tier is not None and tier not in aiws_route.TIERS:
        raise ValueError("tier must be local, flash or pro")
    return app.assistant.start_turn(payload["text"], payload.get("threadId"), tier)


def post_assistant_route(app, payload, p):
    if set(payload) != {"text"} or not isinstance(payload["text"], str):
        raise ValueError("Expected text")
    return app.assistant.route(payload["text"])


def post_assistant_override(app, payload, p):
    _exactly(payload, {"from", "to"}, "Expected from and to")
    return app.assistant.route_override(payload["from"], payload["to"])


def post_plugin_enable(app, payload, p):
    if (not {"name"} <= set(payload) <= {"name", "treeSha256"} or not isinstance(payload["name"], str)
            or not isinstance(payload.get("treeSha256", ""), (str, type(None)))):
        raise ValueError("Expected name and treeSha256")
    return app.assistant.plugin_enable(payload["name"][:64], payload.get("treeSha256"))


def post_plugin_disable(app, payload, p):
    if set(payload) != {"name"} or not isinstance(payload["name"], str):
        raise ValueError("Expected name")
    return app.assistant.plugin_disable(payload["name"][:64])


def post_system(kind):
    return lambda app, payload, p: app.system_op(kind, payload)


def post_ide_start(app, payload, p):
    _empty(payload)
    return app.ide_open(server_only=True)


def post_ide_open(app, payload, p):
    _empty(payload)
    return app.ide_open()


def post_ide_session(app, payload, p):
    if set(payload) - {"path"} or not isinstance(payload.get("path", "."), str):
        raise ValueError("Unexpected fields for this system operation")
    return app.ide_session(payload.get("path", "."))


def post_builder_run(app, payload, p):
    if not {"mandateId", "prompt"} <= set(payload) <= {"mandateId", "prompt", "language"}:
        raise ValueError("Expected mandateId and prompt")
    return app.builder_start(payload["mandateId"], payload["prompt"], "en" if payload.get("language") == "en" else "zh")


def post_mandate_revoke(app, payload, p):
    _empty(payload)
    return app._mandate_view(app.mandates.revoke(p["id"]))


def post_run_stop(app, payload, p):
    _empty(payload)
    app.supervisor.stop(p["id"])
    return {"stopped": True}


def post_run_decide(decision):
    def post(app, payload, p):
        _empty(payload)
        app.supervisor.decide(p["id"], decision == "approve")
        return {"decided": decision}
    return post


def _instruction(call):
    def post(app, payload, p):
        _exactly(payload, {"instruction"}, "Expected instruction")
        return call(app, payload["instruction"])
    return post


def post_handoff(app, payload, p):
    _exactly(payload, {"instruction", "agent"}, "Expected instruction and agent")
    return app.create_handoff(payload["instruction"], payload["agent"])


def post_stage_approve(app, payload, p):
    _empty(payload, "No arguments allowed for approval")
    return app.tasks.approve(p["task"], p["stage"])


def post_stage_dispatch(app, payload, p):
    _empty(payload, "No arguments allowed for dispatch")
    return app.dispatch_stage(p["task"], p["stage"])


POST_ROUTES = _compile([
    ("/api/v1/jobs", post_jobs),
    ("/api/v1/tasks", lambda app, payload, p: app.create_plan(payload)),
    ("/api/v1/tasks/{task}/stages/{stage}/approve", post_stage_approve),
    ("/api/v1/tasks/{task}/stages/{stage}/dispatch", post_stage_dispatch),
    ("/api/v1/model/enable", post_model_toggle(True)),
    ("/api/v1/model/disable", post_model_toggle(False)),
    ("/api/v1/model/suggest", _instruction(lambda app, text: app.local_suggest(text))),
    ("/api/v1/model/plan", _instruction(lambda app, text: app.model_plan(text))),
    ("/api/v1/route", _instruction(lambda app, text: app.route_decision(text))),
    ("/api/v1/route/handoff", post_handoff),
    ("/api/v1/apps/launch", post_apps_launch),
    ("/api/v1/assistant/turn", post_assistant_turn),
    ("/api/v1/assistant/route", post_assistant_route),
    ("/api/v1/assistant/route/override", post_assistant_override),
    ("/api/v1/assistant/plugins/enable", post_plugin_enable),
    ("/api/v1/assistant/plugins/disable", post_plugin_disable),
    ("/api/v1/memory", lambda app, payload, p: app.memory_op(payload)),
    ("/api/v1/cloud/key", lambda app, payload, p: app.cloud_key(payload)),
    ("/api/v1/preview", lambda app, payload, p: app.preview_op("start", payload)),
    ("/api/v1/preview/stop", lambda app, payload, p: app.preview_op("stop", payload)),
    ("/api/v1/system/display", post_system("display")),
    ("/api/v1/system/input", post_system("input")),
    ("/api/v1/system/network", post_system("network")),
    ("/api/v1/system/power", post_system("power")),
    ("/api/v1/ide/start", post_ide_start),
    ("/api/v1/ide/open", post_ide_open),
    ("/api/v1/ide/session", post_ide_session),
    ("/api/v1/builder/mandates", lambda app, payload, p: app.builder_grant(payload)),
    ("/api/v1/builder/mandates/{id}/revoke", post_mandate_revoke),
    ("/api/v1/builder/runs", post_builder_run),
    ("/api/v1/builder/runs/{id}/stop", post_run_stop),
    ("/api/v1/builder/runs/{id}/approve", post_run_decide("approve")),
    ("/api/v1/builder/runs/{id}/deny", post_run_decide("deny")),
])


# ----------------------------------------------------------------------------------------------------- handler
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
            return self.reply(403, _err(exc))
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
        url = urlsplit(self.path)
        fn, params = match(GET_ROUTES, url.path)
        if fn is not None:
            return fn(self, app, parse_qs(url.query), params)
        return self.serve_ui(app, url.path)

    def serve_ui(self, app, path):
        if path == "/":
            try:
                source = (app.ui / "index.html").read_text(encoding="utf-8")
                if "</head>" not in source:
                    raise ValueError("Missing head")
            except (OSError, ValueError):
                return self.reply(503, {"error": "React workbench assets missing"})
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
        fn, params = match(POST_ROUTES, urlsplit(self.path).path)
        if fn is None:
            return self.reply(404, {"error": "Not found"})
        origin = self.headers.get("Origin")
        expected = "http://" + HOST + ":" + str(self.server.server_port)
        if origin is not None and origin != expected:
            return self.reply(403, {"error": "Invalid origin"})
        if not secrets.compare_digest(self.headers.get("X-AIWS-CSRF") or "", self.server.application.csrf):
            return self.reply(403, {"error": "Invalid CSRF"})
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            return self.reply(415, {"error": "JSON required"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self.reply(400, {"error": "Invalid length"})
        if not 0 < length <= MAX_BODY:
            return self.reply(413, {"error": "Request too large or empty"})
        try:
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("Expected JSON object")
            result = fn(self.server.application, payload, params)
        except AgentUnavailable as exc:
            return self.reply(503, _err(exc))
        except PermissionError as exc:
            return self.reply(403, _err(exc))
        except SupervisorError as exc:
            return self.reply(409, _err(exc))
        except LocalAgentError as exc:
            return self.reply({"busy": 409, "unavailable": 503}.get(exc.kind, 400), _err(exc))
        except (ValueError, KeyError, TypeError) as exc:
            return self.reply(400, _err(exc))
        return self.reply(202, result)
