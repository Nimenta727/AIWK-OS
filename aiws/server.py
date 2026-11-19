"""No-dependency HTTP server, bound to 127.0.0.1 with CSRF token and strict routes."""
import argparse
import json
import os
import secrets
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from .router import recommend
from .store import Store
from .tools import inventory, interactive
from .execution import CLIAdapters, QueueEngine
from .policy import public_policy, require
from .singleton import WorkspaceLock
from .gitops import create_task_worktree
from . import __version__

WEB = Path(__file__).resolve().parent.parent / "web"
CONTENT_TYPES = {".html":"text/html; charset=utf-8", ".js":"application/javascript; charset=utf-8", ".css":"text/css; charset=utf-8"}


class AppHandler(BaseHTTPRequestHandler):
    server_version = "AIWS/" + __version__

    def _host_ok(self):
        host = self.headers.get("Host", "").lower()
        return host in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}",
                        "127.0.0.1", "localhost"}

    def _base_headers(self, status=200, ctype="application/json; charset=utf-8", length=0):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()

    def _send(self, value, status=200):
        payload = json.dumps(value,ensure_ascii=False).encode("utf-8")
        self._base_headers(status,length=len(payload))
        self.wfile.write(payload)

    def _error(self, status, message):
        self._send({"error":message},status)

    def _guard(self):
        if not self._host_ok():
            self._error(403, "非法 Host 请求")
            return False
        return True

    def do_GET(self):
        if not self._guard():
            return
        route = urlparse(self.path).path
        if route == "/api/session":
            return self._send({"csrf":self.server.csrf, "version":__version__,
                               "read_only_enabled":self.server.allow_codex_readonly})
        if route == "/api/health":
            return self._send({"version":__version__,"platform":sys.platform,
                               "tools":inventory(),"workspace":str(self.server.store.workspace)})
        if route == "/api/projects":
            return self._send({"projects":self.server.store.projects()})
        if route == "/api/approvals":
            return self._send({"approvals":self.server.store.approvals()})
        if route == "/api/jobs":
            return self._send({"jobs":self.server.store.jobs()})
        if route == "/api/policy":
            return self._send({"capabilities":public_policy(),"adapters":CLIAdapters.inventory()})
        if route == "/api/tasks":
            return self._send({"tasks":[self.server.store.task_view(t) for t in self.server.store.list_tasks()]})
        if route.startswith("/api/tasks/") and route.count("/") == 3:
            try:
                task = self.server.store.get(route.split("/")[-1])
                return self._send({"task":self.server.store.task_view(task)})
            except KeyError:
                return self._error(404,"未找到任务")
        safe_static = {"/":"index.html", "/index.html":"index.html", "/app.js":"app.js", "/app.css":"app.css"}
        if route in safe_static:
            file = WEB / safe_static[route]
            payload = file.read_bytes()
            self._base_headers(200,CONTENT_TYPES[file.suffix],len(payload))
            self.wfile.write(payload)
            return
        self._error(404,"未找到页面")

    def do_POST(self):
        if not self._guard():
            return
        origin = self.headers.get("Origin", "")
        if origin and origin not in (f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"):
            return self._error(403, "跨站请求被拒绝")
        if self.headers.get("X-AIWS-Token") != self.server.csrf:
            return self._error(403,"缺少本地会话令牌")
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            return self._error(415,"只接受 JSON")
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self._error(400,"无效请求长度")
        if n <= 0 or n > 64 * 1024:
            return self._error(413,"请求体超出限制")
        try:
            obj = json.loads(self.rfile.read(n))
            if not isinstance(obj, dict):
                raise ValueError("请求必须是对象")
            self._post_route(urlparse(self.path).path,obj)
        except (ValueError, KeyError, FileNotFoundError, OSError) as exc:
            self._error(400, str(exc))
        except Exception as exc:
            self.server.store.audit("unexpected_error", {"type":type(exc).__name__})
            self._error(500,"服务器内部错误；请查看日志")

    def _post_route(self, route,obj):
        store = self.server.store
        if route == "/api/projects":
            slug = store.create_project(obj.get("name", ""))
            store.audit("create_project",{"name":slug})
            return self._send({"project":slug},201)
        if route == "/api/tasks":
            title = obj.get("title", "")
            description = obj.get("description", "")
            project = obj.get("project", "")
            if not all(isinstance(t,str) for t in (title,description,project)):
                raise ValueError("字段类型必须是字符串")
            pick = recommend(title, description)
            agent = obj.get("agent", "auto")
            if agent == "auto":
                agent = pick["agent"]
            if agent not in ("claude", "codex", "dual", "manual"):
                raise ValueError("未知 Agent")
            task = store.create_task(title.strip(),description.strip(),project,agent,pick["reason"])
            store.audit("create_task",{"id":task["id"],"agent":task["agent"]})
            return self._send({"task":task},201)
        if route.startswith("/api/approvals/"):
            parts = route.strip("/").split("/")
            if len(parts) != 4 or parts[:2] != ["api", "approvals"] or parts[3] != "decide":
                return self._error(404,"未知审批操作")
            if not self.server.allow_codex_readonly:
                return self._error(403,"后台队列未启用")
            result = store.decide(parts[2],obj.get("decision"))
            if result["job_id"] is not None:
                self.server.engine.wake()
            return self._send(result)
        if route.startswith("/api/jobs/"):
            parts = route.strip("/").split("/")
            if len(parts) != 4 or parts[:2] != ["api", "jobs"] or parts[3] != "cancel":
                return self._error(404,"未知队列操作")
            store.cancel_queued(parts[2])
            return self._send({"cancelled":parts[2]})
        if route.startswith("/api/tasks/"):
            parts = route.strip("/").split("/")
            if len(parts) != 4 or parts[:2] != ["api", "tasks"]:
                return self._error(404,"未知任务操作")
            task_id, action = parts[2], parts[3]
            task = store.get(task_id)
            if action == "prepare":
                path = store.task_brief(task_id)
                store.audit("prepare_task",{"id":task_id})
                return self._send({"task":store.get(task_id),"brief":str(path)})
            if action == "launch":
                agent = obj.get("agent", task["agent"])
                if agent not in ("claude","codex"):
                    raise ValueError("选择 Claude 或 Codex 进行交互式执行")
                step = store.active_step(task_id)
                if task["status"] != "prepared" or step is None or step["status"] != "prepared":
                    raise ValueError("请先生成当前阶段交接文档")
                if step["agent"] != "manual" and step["agent"] != agent:
                    raise ValueError("当前阶段只能调用规划的 Agent")
                require("launch_official_cli")
                interactive(agent,store.task_workspace(task_id))
                store.audit("launch_interactive",{"id":task_id,"agent":agent})
                return self._send({"launched":agent,"brief":str(store.tasks_root / (task_id + ".md"))})
            if action == "worktree":
                require("git_worktree", confirmed=obj.get("confirmed") is True)
                if task["status"] != "pending":
                    raise ValueError("请在生成交接文档之前创建隔离工作区")
                path = create_task_worktree(task,store)
                return self._send({"path":str(path),"task":store.task_view(task)},201)
            if action == "step-finish":
                updated = store.finish_step(task_id,obj.get("state"),obj.get("result"))
                store.audit("workflow_step_finished",{"id":task_id,"state":obj.get("state")})
                return self._send({"task":updated})
            if action == "request-readonly":
                if not self.server.allow_codex_readonly:
                    return self._error(403,"实验性只读后台执行未启用")
                approval = store.request_readonly(task_id)
                return self._send({"approval":approval},201)
            if action == "codex-readonly":
                return self._error(403,"V0.3 要求先申请一次性审批，再通过审批中心启动队列")
            if action == "complete":
                if task["status"] == "running":
                    raise ValueError("后台执行中的任务不能手动完成")
                state = obj.get("state")
                if state not in ("done","failed"):
                    raise ValueError("状态必须是 done 或 failed")
                updated = store.finish_step(task_id,state,obj.get("result", ""))
                store.audit("complete_task",{"id":task_id,"state":state})
                return self._send({"task":updated})
        return self._error(404,"未知操作")

    def log_message(self, format, *args):
        # No request bodies, no session tokens, no sensitive CLI output.
        pass


class WorkstationServer(ThreadingHTTPServer):
    def server_close(self):
        if getattr(self, "engine", None):
            self.engine.stop()
        if getattr(self, "workspace_lock", None):
            self.workspace_lock.release()
        super().server_close()


def make_server(workspace: Path, port=8765, *, allow_codex_readonly=False, executor=None):
    if port != 0 and (port < 1024 or port > 65535):
        raise ValueError("端口必须在 1024 到 65535 之间")
    locker = WorkspaceLock(workspace).acquire()
    try:
        httpd = WorkstationServer(("127.0.0.1",port),AppHandler)
        httpd.workspace_lock = locker
        httpd.store = Store(workspace)
    except Exception:
        locker.release()
        raise
    httpd.csrf = secrets.token_urlsafe(32)
    httpd.allow_codex_readonly = allow_codex_readonly
    httpd.engine = QueueEngine(httpd.store) if executor is None else QueueEngine(httpd.store,executor=executor)
    if allow_codex_readonly:
        httpd.engine.start()
    return httpd


def main():
    parser = argparse.ArgumentParser(description="AIWS Windows local dashboard")
    parser.add_argument("--workspace", default=os.environ.get("AIWS_WORKSPACE", str(Path.home() / "AI-Workstation")))
    parser.add_argument("--port",type=int,default=8765)
    parser.add_argument("--no-browser",action="store_true")
    parser.add_argument("--enable-codex-readonly", action="store_true", help="Opt-in to experimental read-only Codex exec")
    args = parser.parse_args()
    httpd = make_server(Path(args.workspace),args.port,allow_codex_readonly=args.enable_codex_readonly)
    url = f"http://127.0.0.1:{httpd.server_port}"
    print(f"AIWS {__version__} listening at {url}; workspace={httpd.store.workspace}")
    if not args.no_browser:
        import threading
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()

if __name__ == "__main__":
    main()
