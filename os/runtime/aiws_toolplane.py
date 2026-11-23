"""AIWS OS guest tool plane. Python stdlib first; runs as the invoking guest user.

Not an OS sandbox or a privileged broker. Host protection belongs to the hypervisor.

This module is the plane's contract: the tool catalog, tool classes (READ/FILE_WRITE/APP_LAUNCH), workspace
containment (_workspace, _path), argument checks and dispatch (invoke). The tools themselves live in
aiws_tools_files.py (file operations) and aiws_tools_system.py (system, network, downloads, git, runtimes, browser).
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from aiws_guest_boundary import protect_guest_workspace
import time
import aiws_exttools

MAX_TEXT = 128 * 1024
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "target", "dist", "build", ".aiws-trash"}
TRASH = ".aiws-trash"
MAX_COPY_BYTES = 64 * 1024 * 1024
MAX_TREE_ENTRIES = 5000
MAX_TRASH_ITEMS = 500
TOOL_SPECS = [
    ("workspace.tree", "List bounded workspace files without following symlinks", {"path": "string"}),
    ("file.read", "Read a UTF-8 file and its SHA-256", {"path": "string"}),
    ("system.info", "Read-only local OS facts: kernel, uptime, load, memory, workspace disk usage", {}),
    ("network.status", "Read-only LOCAL network state from the kernel (interfaces, addresses, route, DNS config, socket counts, throughput). Sends no packets", {}),
    ("download.list", "List downloads in the workspace downloads/ folder with complete/partial state (reads files only; cannot download)", {}),
    ("download.progress", "Progress of one partial download under downloads/: size, growth rate, percent if a .progress.json sidecar gives totalBytes", {"path": "string"}),
    ("file.stat", "Read type, size, mtime and SHA-256 (directories: bounded tree fingerprint)", {"path": "string"}),
    ("file.trashList", "List items in the reversible workspace trash (id, original path, type, time)", {}),
    ("file.mkdir", "Create one new directory; parent must exist; guest workspace write", {"path": "string"}),
    ("file.copy", "Copy one regular file (<=64MiB) to a new path; never overwrites; guest workspace write", {"path": "string", "to": "string", "expectedSha256": "string"}),
    ("file.move", "Move or rename a file or directory to a new path; never overwrites; fingerprint precondition", {"path": "string", "to": "string", "expectedSha256": "string"}),
    ("file.trash", "Move a file or directory to the reversible workspace trash; never deletes permanently", {"path": "string", "expectedSha256": "string"}),
    ("file.restore", "Restore a trashed item to its original path if still free", {"trashId": "string"}),
    ("file.replace", "Atomically replace a file with SHA-256 precondition; guest workspace write", {"path": "string", "text": "string", "expectedSha256": "string"}),
    ("tools.list", "List the integrated applications and command-line tools of this workstation and whether each is installed (read-only)", {}),
    ("doc.text", "Extract plain text from a workspace document: PDF (pdftotext), DOCX/ODT/EPUB (pandoc), HTML, or any small text file; bounded output", {"path": "string"}),
    ("app.launch", "Start a registered desktop program (terminal, browser, editor ...). Needs the user's explicit approval; fixed command, no arguments", {"id": "string"}),
    ("code.search", "Search literal text in source files with bounded output", {"query": "string", "path": "string"}),
    ("log.digest", "Compress a long text log: identical messages are merged (numbers ignored) and each is shown verbatim with the FIRST line number where it appeared and how often it repeated; rare messages are kept first. Use it before reading a long log, then log.lines around a line number", {"path": "string"}),
    ("log.lines", "Show the numbered lines start..end (at most 200) of a workspace text file or log. start and end are plain numbers such as 340 and 360 (the number after the L in a log.digest entry), not text", {"path": "string", "start": "string", "end": "string"}),
    ("git.inspect", "Read git status or diff (not commit/push)", {"view": "string"}),
    ("runtime.detect", "Discover installed language and build executables", {}),
    ("runtime.test", "Execute a fixed language test command in the guest workspace; opt-in", {"language": "string"}),
    ("browser.local_text", "Extract text from an HTML document in the workspace", {"path": "string"}),
    ("browser.snapshot", "Headless Chromium DOM-text snapshot; disabled until exact origins are configured", {"url": "string"}),
]

def catalog():
    tools = []
    for name, description, fields in TOOL_SPECS + aiws_exttools.specs():
        properties = {key: {"type": value} for key, value in fields.items()}
        required = (aiws_exttools.required(name) if name in aiws_exttools.EXT else
                    ["id"] if name == "app.launch" else
                    ["query"] if name == "code.search" else
                    list(fields) if name in {"log.digest", "log.lines", "doc.text", "download.progress", "file.read", "file.replace", "file.stat", "file.mkdir", "file.copy", "file.move", "file.trash", "file.restore", "browser.local_text", "browser.snapshot", "runtime.test"} else [])
        tools.append({"name": name, "description": description, "inputSchema": {
            "type": "object", "properties": properties, "required": required, "additionalProperties": False}})
    return tools

# Executables `runtime.detect` reports (path or null). Languages first, then build, debug, VCS and editors.
DETECT_TOOLS = (
    "python3", "pipx", "node", "npm", "tsc", "go", "rustc", "cargo", "javac", "java", "mvn", "ruby", "php", "lua5.4",
    "cc", "gcc", "g++", "clang", "clangd", "cmake", "make", "ninja", "meson",
    "gdb", "valgrind", "shellcheck", "sqlite3", "psql",
    "git", "gh", "rg", "jq", "tmux", "nvim", "vim", "aiws-code", "chromium", "chromedriver",
)

# Single source of truth for tool classes. Every other module imports these.
READ_TOOLS = frozenset({
    "workspace.tree", "file.read", "file.stat", "tools.list", "doc.text", "file.trashList", "code.search", "git.inspect", "log.digest", "log.lines",
    "runtime.detect", "browser.local_text",
    "system.info", "network.status", "download.list", "download.progress",
}) | aiws_exttools.names()
# Desktop launches are write-class: they always become pending DAG stages that need the user's approval, and they are
# EXECUTED by the workbench's desktop launcher (aiws_launcher.py), because only it can reach the display.
APP_LAUNCH_TOOLS = frozenset({"app.launch"})
FILE_WRITE_TOOLS = frozenset({"file.replace", "file.mkdir", "file.copy", "file.move",
                              "file.trash", "file.restore"})

def _workspace():
    value = os.environ.get("AIWS_WORKSPACE", "").strip()
    if not value:
        raise ValueError("AIWS_WORKSPACE must point to a user-selected guest project directory")
    raw = Path(value).expanduser()
    if not raw.is_absolute() or raw.is_symlink() or not raw.is_dir():
        raise ValueError("Workspace must be an existing non-symlink absolute directory")
    root = raw.resolve(strict=True)
    if root == Path("/") or root == Path.home():
        raise ValueError("Guest root or entire home is not an acceptable workspace")
    protect_guest_workspace(root)
    return root

def _path(root, value=".", allow_missing=False):
    if not isinstance(value, str) or not value or len(value) > 512:
        raise ValueError("Invalid workspace path")
    if "\\" in value:
        raise ValueError("Use slash-separated relative paths")
    relative = Path(value)
    if relative.is_absolute() or any(part in ("..", ".git", ".ssh") for part in relative.parts):
        raise ValueError("Path outside workspace or protected metadata is not allowed")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Symlink paths are not supported")
    resolved = current.resolve(strict=False)
    if not resolved.is_relative_to(root):
        raise ValueError("Workspace path escape")
    protect_guest_workspace(root, resolved)
    if not allow_missing and not resolved.exists():
        raise FileNotFoundError(value)
    return resolved

def _text_file(path):
    if not path.is_file() or path.stat().st_size > MAX_TEXT:
        raise ValueError("File is not a regular small text file")
    return path.read_text(encoding="utf-8")


DOC_MAX_BYTES = 32 * 1024 * 1024
DOC_TEXT_LIMIT = 64 * 1024
PANDOC_SUFFIXES = {".docx": "docx", ".odt": "odt", ".epub": "epub", ".rtf": "rtf"}

def _safe_env():
    blocked = ("TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "API_KEY", "OPENAI_", "ANTHROPIC_", "GITHUB_", "AWS_", "AZURE_")
    env = {k: v for k, v in os.environ.items() if not any(fragment in k.upper() for fragment in blocked)}
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env

def _command(root, argv, timeout=20):
    result = subprocess.run(argv, cwd=root, env=_safe_env(), capture_output=True,
                            text=True, errors="replace", timeout=timeout, check=False)
    return {"argv": argv, "exitCode": result.returncode,
            "stdout": result.stdout[:24000], "stderr": result.stderr[:12000],
            "truncated": len(result.stdout) > 24000 or len(result.stderr) > 12000}


def _handlers():
    """name -> handler(root, arguments). Built on first use: the tool modules import helpers from this module."""
    global _HANDLERS
    if _HANDLERS is None:
        import aiws_tools_files as f
        import aiws_tools_system as s
        _HANDLERS = {
            "workspace.tree": f._tree, "file.read": f._file_read, "file.replace": f._replace,
            "log.digest": f._log_digest, "log.lines": f._log_lines,
            "file.stat": f._stat, "file.trashList": f._trash_list, "file.mkdir": f._mkdir, "file.copy": f._copy,
            "file.move": f._move, "file.trash": f._trash, "file.restore": f._restore,
            "doc.text": f._doc_text, "code.search": f._search,
            "system.info": s._system_info, "network.status": s._network_status,
            "download.list": s._download_list, "download.progress": s._download_progress,
            "tools.list": s._tools_list, "git.inspect": s._git, "runtime.test": s._runtime,
            "runtime.detect": lambda root, a: {"tools": {p: shutil.which(p) for p in DETECT_TOOLS}},
            "browser.local_text": lambda root, a: {"path": a["path"], "text": s._extract(_text_file(_path(root, a["path"])))},
            "browser.snapshot": s._browser,
        }
    return _HANDLERS

_HANDLERS = None

def invoke(name, arguments):
    if not isinstance(arguments, dict):
        raise ValueError("Arguments must be an object")
    specs = {tool["name"]: tool for tool in catalog()}
    if name not in specs:
        raise ValueError("Unknown tool: " + str(name))
    fields = specs[name]["inputSchema"]
    if set(arguments) - set(fields["properties"]):
        raise ValueError("Unexpected tool argument")
    if any(key not in arguments for key in fields["required"]):
        raise ValueError("Missing required tool argument")
    root = _workspace()
    if name == "app.launch":
        raise PermissionError("app.launch is executed by the desktop launcher after approval, not by the tool plane")
    if name in aiws_exttools.EXT:
        return aiws_exttools.run(name, arguments, root, _path, _safe_env())
    handler = _handlers().get(name)
    if handler is None:
        raise AssertionError("Unreachable tool dispatch")
    return handler(root, arguments)


def audit(name, arguments, ok):
    """Best-effort local correlation, not tamper-resistant proof (guest agent can edit it)."""
    try:
        state = Path(os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local/state")) / "aiws"
        state.mkdir(mode=0o700, parents=True, exist_ok=True)
        record = {"time": time.time(), "tool": name, "ok": ok,
                  "argsSha256": hashlib.sha256(json.dumps(arguments, sort_keys=True).encode()).hexdigest()}
        with (state / "toolcalls.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, separators=(",", ":")) + "\n")
    except (OSError, TypeError, ValueError):
        pass
