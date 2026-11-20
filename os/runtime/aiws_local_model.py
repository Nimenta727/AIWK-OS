"""Optional offline AIWS OS 1-3B model inference gateway.

The model is ONLY a constrained guest-tool suggestion service. It cannot call
tools itself, access files, run commands, or make HTTP requests to the host.
The sole model URL is hardcoded IPv4 guest loopback with proxies disabled.
"""
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

HOST = "127.0.0.1"
PORT = 18080
MODEL_ALIAS = "aiws-local"
MAX_INTENT = 1000
READ_TOOLS = frozenset({
    "workspace.tree", "file.read", "code.search", "git.inspect", "runtime.detect",
    "browser.local_text", "platform.inspect", "code.symbols", "code.references",
    "code.dependencies", "code.platformApis",
})

class LocalModelError(ValueError):
    pass

class LocalPlanner:
    def __init__(self, enabled=None, port=PORT):
        # The port is internal/test-only. Neither API clients nor model content
        # may choose an inference URL or point the connection at the host.
        marker = Path.home() / ".config/aiws/local-model-enabled"
        persisted = marker.is_file() and not marker.is_symlink() and marker.read_text().strip() == "1"
        self.enabled = ((os.environ.get("AIWS_LOCAL_MODEL_ENABLED") == "1") or persisted) if enabled is None else enabled
        if not isinstance(port, int) or not (1 <= port <= 65535):
            raise LocalModelError("Invalid localhost inference port")
        self.url = "http://" + HOST + ":" + str(port)
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def status(self):
        status = {"mode": "optional-guest-only", "configured": bool(self.enabled),
                  "provider": "llama.cpp", "model": MODEL_ALIAS,
                  "network": "guest-loopback-only",
                  "automaticExecution": False, "cloudFallback": False,
                  "online": False,
                  "cpuOnly": True,
                  "weightsPresent": (not (Path.home()/".local/share/aiws/models/aiws-local.gguf").is_symlink() and
                                     (Path.home()/".local/share/aiws/models/aiws-local.gguf").is_file())}
        if self.enabled:
            try:
                with self.opener.open(self.url + "/health", timeout=1.5) as response:
                    status["online"] = response.status == 200
            except (OSError, urllib.error.URLError, TimeoutError):
                pass
        return status

    @staticmethod
    def validate(proposal):
        from aiws_toolplane import catalog
        if not isinstance(proposal, dict) or set(proposal) != {"tool", "arguments", "reason"}:
            raise LocalModelError("Model proposal must contain exactly tool, arguments and reason")
        tool, args, reason = proposal["tool"], proposal["arguments"], proposal["reason"]
        if not isinstance(tool, str) or tool not in READ_TOOLS:
            raise LocalModelError("Model tried a non-read-only or host tool")
        specs = {x["name"]: x["inputSchema"] for x in catalog()}
        spec = specs[tool]
        if not isinstance(args, dict) or any(k not in spec["properties"] for k in args):
            raise LocalModelError("Model proposal contains unknown tool arguments")
        if any(k not in args for k in spec["required"]):
            raise LocalModelError("Model proposal omitted required arguments")
        if any(not isinstance(v, str) or len(v) > 512 for v in args.values()):
            raise LocalModelError("Model tool arguments must be bounded strings")
        for k in ("path",):
            if k in args:
                p = Path(args[k])
                if not args[k] or p.is_absolute() or ".." in p.parts or "\\" in args[k]:
                    raise LocalModelError("Model attempted to escape guest workspace")
        if not isinstance(reason, str) or len(reason) > 500:
            raise LocalModelError("Invalid model rationale")
        return {"tool": tool, "arguments": args, "reason": reason,
                "requiresReview": True, "executed": False, "source": "local-model"}

    def suggest(self, instruction):
        if not self.enabled:
            raise LocalModelError("No local model configured; deterministic guest tools remain available")
        if not isinstance(instruction, str) or not (1 <= len(instruction) <= MAX_INTENT):
            raise LocalModelError("Intent must contain 1-1000 characters")
        system = (
            "You are the AIWS OS guest-local planning assistant. Reply with exactly "
            "one JSON object with keys tool, arguments, reason. You are NOT an executor. "
            "Only recommend read-only guest tools: "
            + ", ".join(sorted(READ_TOOLS)) + ". "
            "Never use shell, root, networking, kernel mutation, host file paths, "
            "hypervisor control, device passthrough or cloud calls. "
            "All paths must be relative to a dedicated guest project workspace. "
            "Use the smallest possible tool arguments. Do not quote or reveal secrets. "
            "If the user requests destructive changes, propose a read-only inspection instead."
        )
        payload = {
            "model": MODEL_ALIAS, "stream": False,
            "temperature": 0.1, "max_tokens": 256,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": instruction}],
        }
        request = urllib.request.Request(
            self.url + "/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with self.opener.open(request, timeout=40) as response:
                data = response.read(16385)
                if len(data) > 16384:
                    raise LocalModelError("Local model response size limit exceeded")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise LocalModelError("Local guest inference service unavailable") from exc
        try:
            response = json.loads(data)
            proposal = json.loads(response["choices"][0]["message"]["content"])
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LocalModelError("Model returned invalid structured JSON") from exc
        return self.validate(proposal)
