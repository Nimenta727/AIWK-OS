"""Same-user local UNIX transport to the systemd guest task scheduler."""
import json
from pathlib import Path
import socket
from aiws_agent_service import socket_path, AgentError
from aiws_guest_ops import READ_TOOLS

class AgentUnavailable(ConnectionError):
    pass

class AgentClient:
    def __init__(self,path=None):
        self.path=Path(path) if path is not None else socket_path()

    def request(self,op,args=None):
        raw=(json.dumps({"op":op,"args":args if args is not None else {}},
             separators=(",",":"),ensure_ascii=False)+"\n").encode()
        if len(raw)>24576:
            raise AgentError("Agent request too large")
        try:
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as conn:
                conn.settimeout(12)
                conn.connect(str(self.path))
                conn.sendall(raw)
                data=b""
                while not data.endswith(b"\n"):
                    chunk=conn.recv(65536)
                    if not chunk:
                        raise AgentUnavailable("Guest agent disconnected")
                    data+=chunk
                    if len(data)>1024*1024:
                        raise AgentError("Agent response too large")
            response=json.loads(data)
        except (OSError,TimeoutError) as exc:
            raise AgentUnavailable("Dedicated guest Agent system service unavailable") from exc
        if not isinstance(response,dict) or not isinstance(response.get("ok"),bool):
            raise AgentError("Invalid Agent socket response")
        if not response["ok"]:
            raise AgentError(str(response.get("error","Guest Agent rejected request"))[:240])
        return response["result"]

class TaskProxy:
    def __init__(self,agent):
        self.agent=agent
    def list(self):
        return self.agent.request("task.list")
    def get(self,identifier):
        return self.agent.request("task.get",{"id":identifier})
    def audit(self,identifier):
        return self.agent.request("task.audit",{"id":identifier})
    def create(self,title,goal,stages):
        return self.agent.request("task.create",{"title":title,"goal":goal,"stages":stages})
    def import_windows(self,worktask):
        return self.agent.request("task.import_windows",{"task":worktask})
    def approve(self,identifier,key):
        return self.agent.request("task.approve",{"id":identifier,"key":key})
    def dispatch(self,identifier,key):
        return self.agent.request("task.dispatch",{"id":identifier,"key":key})
    def model_plan(self,instruction,proposal):
        return self.agent.request("task.model",{"instruction":instruction,"proposal":proposal})
    def verify_audit(self):
        return self.agent.request("audit.verify")
    def close(self):
        pass

class ReadOnlySystemProxy:
    def __init__(self,agent):
        self.agent=agent
    def execute(self,tool,args,*,approved=False):
        if approved or tool not in READ_TOOLS:
            raise AgentError("Guest system writes must be approved as persistent DAG stages")
        return self.agent.request("guest.read",{"tool":tool,"arguments":args})

class ReadOnlyToolProxy:
    def __init__(self,agent):
        self.agent=agent
    def invoke(self,tool,args):
        return self.agent.request("tool.read",{"tool":tool,"arguments":args})
