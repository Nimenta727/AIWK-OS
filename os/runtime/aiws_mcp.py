"""AIWS guest MCP: read-only requests always go through Agent/Broker IPC.

The underlying Python toolplane is not a same-UID security sandbox.
"""
import json
import sys
from aiws_toolplane import catalog
from aiws_agent_client import AgentClient
from aiws_permission_broker import DIRECT_READ

MCP_CATALOG = [item for item in catalog() if item["name"] in DIRECT_READ]
MCP_TOOLS = frozenset(item["name"] for item in MCP_CATALOG)

VERSION = "2025-11-25"

def handle(message):
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return {"jsonrpc": "2.0", "id": None,
                "error": {"code": -32600, "message": "Invalid JSON-RPC request"}}
    request_id = message.get("id")
    if request_id is None:
        return None  # MCP notification; no response
    method = message.get("method")
    params = message.get("params") or {}
    if not isinstance(params, dict):
        return {"jsonrpc": "2.0", "id": request_id,
                "error": {"code": -32602, "message": "Invalid params"}}
    if method == "initialize":
        result = {"protocolVersion": VERSION,
                  "capabilities": {"tools": {}},
                  "serverInfo": {"name": "aiws-os-guest-tools", "version": "0.1.0"}}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": MCP_CATALOG}
    elif method == "tools/call":
        name, args = params.get("name"), params.get("arguments", {})
        try:
            if name not in MCP_TOOLS:
                raise PermissionError("MCP only permits read-only tools via Agent/Broker")
            data = AgentClient().request("tool.read", {"tool": name,
                                                     "arguments": args})
            result = {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
                      "isError": False}
        except (ValueError, PermissionError, FileNotFoundError, OSError,
                RuntimeError, TimeoutError, subprocess_exception()) as error:
            result = {"content": [{"type": "text", "text": str(error)}], "isError": True}
    else:
        return {"jsonrpc": "2.0", "id": request_id,
                "error": {"code": -32601, "message": "Method not found"}}
    return {"jsonrpc": "2.0", "id": request_id, "result": result}

def subprocess_exception():
    import subprocess
    return subprocess.TimeoutExpired

def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--list":
        print(json.dumps({"tools": MCP_CATALOG}, ensure_ascii=False))
        return
    for line in sys.stdin:
        try:
            request = json.loads(line)
            response = handle(request)
        except (json.JSONDecodeError, UnicodeError) as error:
            response = {"jsonrpc": "2.0", "id": None,
                        "error": {"code": -32700, "message": str(error)}}
        except Exception as error:
            response = {"jsonrpc": "2.0", "id": None,
                        "error": {"code": -32603, "message": type(error).__name__}}
        if response is not None:
            print(json.dumps(response, ensure_ascii=False), flush=True)

if __name__ == "__main__":
    main()
