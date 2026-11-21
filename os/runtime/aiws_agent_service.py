"""Independent, systemd-supervised unprivileged AIWS guest Agent.

The dashboard communicates over a same-UID AF_UNIX socket, never a privileged
host bridge. Guest service/kernel writes are always reviewed SQLite DAG steps.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import socket
import socketserver
import struct
from aiws_guest_boundary import protect_guest_workspace, require_guest_runtime
from aiws_guest_ops import GuestOperations, TOOLS as SYSTEM_TOOLS, READ_TOOLS
from aiws_local_model import LocalPlanner, stages_from_proposal
from aiws_tasks import GuestTaskStore, TaskError
from aiws_permission_broker import BrokerClient, BrokerDenied
from aiws_toolplane import invoke, audit, catalog as tool_catalog, READ_TOOLS as PLANE_READ_TOOLS

class AgentError(ValueError):
    pass

def socket_path():
    expected=Path("/run/user")/str(os.getuid())
    if (Path(os.environ.get("XDG_RUNTIME_DIR",""))!=expected or
            expected.is_symlink() or not expected.is_dir()):
        raise PermissionError("Dedicated guest user runtime directory required")
    return expected/"aiws-agent"/"agent.sock"

class AgentCore:
    def __init__(self,workspace,state,singleton=True,broker=None):
        self.broker=broker if broker is not None else BrokerClient()
        self.workspace=Path(workspace).resolve(strict=True)
        self.tasks=GuestTaskStore(Path(state)/"aiws",singleton=singleton)
        self.ops=GuestOperations(self.workspace,Path(state)/"aiws/kernel-candidates")
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix="aiws-durable")

    def close(self):
        self.pool.shutdown(wait=True,cancel_futures=True)
        self.tasks.close()

    def _run(self,action):
        tid,key=action["task_id"],action["stage_key"]
        try:
            self.tasks.started(tid,key)
            tool,args=action["tool"],action["arguments"]
            # Policy is bound to the exact persisted, running DAG state.
            # A missing Broker is a failed execution, never a permissive fallback.
            self.broker.authorize_stage(tid,key,tool,args)
            result=(self.ops.execute(tool,args,approved=action["approvalGranted"])
                    if tool in SYSTEM_TOOLS else invoke(tool,args))
            serial=json.dumps(result,ensure_ascii=False)
            if len(serial)>65536:
                result={"truncated":True,"preview":serial[:32000]}
            self.tasks.finished(tid,key,result=result)
            audit(tool,args,True)
        except Exception as exc:
            try:
                self.tasks.finished(tid,key,error=(type(exc).__name__+": "+str(exc))[:240])
            except TaskError:
                pass
            audit(action["tool"],action["arguments"],False)

    def handle(self,req):
        if not isinstance(req,dict) or set(req)!={"op","args"} or not isinstance(req["args"],dict):
            raise AgentError("Expected op and args")
        op,a=req["op"],req["args"]
        if op=="health":
            fields(a,set())
            try:
                self.broker.authorize_read("runtime.detect",{})
                broker_ready=True
            except (BrokerDenied,OSError):
                broker_ready=False
            return {"ready":True,"scope":"guest-user","engine":"persistent-systemd-dag",
                    "brokerReady":broker_ready,"brokerScope":"same-uid-policy-only"}
        if op=="task.list":
            fields(a,set())
            return self.tasks.list()
        if op=="task.get":
            fields(a,{"id"})
            return self.tasks.get(a["id"])
        if op=="task.audit":
            fields(a,{"id"})
            return self.tasks.audit(a["id"])[-128:]
        if op=="task.import_windows":
            fields(a,{"task"})
            return self.tasks.import_windows(a["task"])
        if op=="task.create":
            fields(a,{"title","goal","stages"})
            return self.tasks.create(a["title"],a["goal"],a["stages"])
        if op=="task.approve":
            fields(a,{"id","key"})
            return self.tasks.approve(a["id"],a["key"])
        if op=="task.dispatch":
            fields(a,{"id","key"})
            action=self.tasks.dispatch(a["id"],a["key"])
            self.pool.submit(self._run,action)
            return self.tasks.get(a["id"])
        if op=="task.overview":
            fields(a,set())
            return self.tasks.overview()
        if op=="task.route":
            fields(a,{"id","route"})
            return self.tasks.record_route(a["id"],a["route"])
        if op=="task.model":
            fields(a,{"instruction","proposal"})
            if not isinstance(a["instruction"],str) or not 1<=len(a["instruction"])<=1000:
                raise AgentError("Invalid bounded instruction")
            # Independent revalidation of the raw model shape. The Agent (not the model, not the
            # UI) reads the real files and computes every fingerprint for approval-gated writes.
            proposal=LocalPlanner.validate_any(a["proposal"])
            if proposal["tool"] == "refuse":
                raise AgentError("Refusals cannot become executable Agent stages")
            stages=stages_from_proposal(proposal,lambda p: invoke("file.stat",{"path":p}))
            title=("Local plan: %d steps"%len(stages)) if "steps" in proposal else "Local proposal: "+proposal["tool"]
            task=self.tasks.create(title,proposal["reason"],stages)
            self.tasks.record_model_proposal(task["task"]["id"],"aiws-local",
                                             a["instruction"],proposal)
            return self.tasks.get(task["task"]["id"])
        if op=="audit.verify":
            fields(a,set())
            return self.tasks.verify_audit()
        if op=="tool.read":
            fields(a,{"tool","arguments"})
            readonly=PLANE_READ_TOOLS
            if a["tool"] not in readonly:
                raise AgentError("Direct guest tool IPC limited to read-only actions")
            if not isinstance(a["arguments"],dict):
                raise AgentError("Tool arguments object required")
            spec=next((t["inputSchema"] for t in tool_catalog() if t["name"]==a["tool"]),None)
            if spec is None or set(a["arguments"])-set(spec["properties"]) or any(
                    k not in a["arguments"] for k in spec["required"]):
                raise AgentError("Invalid read-only tool arguments")
            self.broker.authorize_read(a["tool"],a["arguments"])
            result=invoke(a["tool"],a["arguments"])
            audit(a["tool"],a["arguments"],True)
            return result
        if op=="guest.read":
            fields(a,{"tool","arguments"})
            if a["tool"] not in READ_TOOLS:
                raise AgentError("Guest direct system operations are read-only")
            self.broker.authorize_read(a["tool"],a["arguments"])
            return self.ops.execute(a["tool"],a["arguments"])
        raise AgentError("Unknown guest Agent operation")

def fields(args,keys):
    if set(args)!=keys:
        raise AgentError("Unexpected Agent arguments")

class _Handler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            if not hasattr(socket,"SO_PEERCRED"):
                raise PermissionError("Peer credentials unavailable")
            _pid,uid,_gid=struct.unpack("3i",
                self.request.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
            if uid!=os.getuid():
                raise PermissionError("Agent IPC peer UID not authorized")
            packet=self.rfile.readline(24577)
            if not packet or len(packet)>24576 or not packet.endswith(b"\n"):
                raise AgentError("Invalid bounded Agent request")
            response={"ok":True,"result":self.server.core.handle(json.loads(packet))}
        except (ValueError,PermissionError,TypeError,KeyError,UnicodeError) as exc:
            response={"ok":False,"error":(type(exc).__name__+": "+str(exc))[:240]}
        except Exception as exc:
            response={"ok":False,"error":"Guest Agent failure: "+type(exc).__name__}
        out=(json.dumps(response,ensure_ascii=False,separators=(",",":"))+"\n").encode()
        if len(out)>1024*1024:
            out=b'{"ok":false,"error":"Agent reply exceeds limit"}\n'
        try:
            self.wfile.write(out)
        except OSError:
            pass

class AgentServer(socketserver.ThreadingMixIn,socketserver.UnixStreamServer):
    daemon_threads=True
    allow_reuse_address=False

def serve(core,path):
    path=Path(path)
    if path.parent.is_symlink() or not path.parent.is_dir() or path.parent.stat().st_mode & 0o077:
        raise PermissionError("Agent socket directory must be private")
    if path.exists() or path.is_symlink():
        raise AgentError("Agent socket already exists")
    server=AgentServer(str(path),_Handler)
    server.core=core
    os.chmod(path,0o600)
    return server

def main():
    require_guest_runtime()
    home=Path.home().resolve(strict=True)
    workspace=Path(os.environ.get("AIWS_WORKSPACE",str(home/".local/share/aiws/projects"))).expanduser()
    state=Path(os.environ.get("XDG_STATE_HOME",str(home/".local/state"))).expanduser()
    for path in (workspace,state):
        if not path.is_absolute() or path.is_symlink() or not path.resolve().is_relative_to(home):
            raise PermissionError("Guest paths must be inside the dedicated guest user home")
        path.mkdir(mode=0o700,parents=True,exist_ok=True)
        protect_guest_workspace(path.resolve(strict=True))
    # The tool plane needs an explicit workspace; systemd user units do not
    # inherit the shell's AIWS_WORKSPACE variable.
    os.environ["AIWS_WORKSPACE"]=str(workspace.resolve(strict=True))
    endpoint=socket_path()
    endpoint.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    core=AgentCore(workspace,state,singleton=True)
    try:
        server=serve(core,endpoint)
        try:
            print("AIWS_AGENT_SOCKET_READY",flush=True)
            server.serve_forever(poll_interval=.2)
        finally:
            server.server_close()
            endpoint.unlink(missing_ok=True)
    finally:
        core.close()

if __name__=="__main__":
    main()
