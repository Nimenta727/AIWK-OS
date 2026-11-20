"""AIWS OS guest tool plane. Python stdlib first; runs as the invoking guest user.

Not an OS sandbox or a privileged broker. Host protection belongs to the hypervisor.
"""
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from aiws_crossplatform import inspect_project, scaffold_project
import time
from urllib.parse import urlsplit

MAX_TEXT = 128 * 1024
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "target", "dist", "build"}
TOOL_SPECS = [
    ("workspace.tree", "List bounded workspace files without following symlinks", {"path": "string"}),
    ("file.read", "Read a UTF-8 file and its SHA-256", {"path": "string"}),
    ("file.replace", "Atomically replace a file with SHA-256 precondition; guest workspace write", {"path": "string", "text": "string", "expectedSha256": "string"}),
    ("code.search", "Search literal text in source files with bounded output", {"query": "string", "path": "string"}),
    ("git.inspect", "Read git status or diff (not commit/push)", {"view": "string"}),
    ("runtime.detect", "Discover installed language and build executables", {}),
    ("runtime.test", "Execute a fixed language test command in the guest workspace; opt-in", {"language": "string"}),
    ("browser.local_text", "Extract text from an HTML document in the workspace", {"path": "string"}),
    ("browser.snapshot", "Headless Chromium DOM-text snapshot; disabled until exact origins are configured", {"url": "string"}),
    ("platform.inspect", "Recognize Windows/macOS/Swift project sources without building", {"path": "string"}),
    ("project.scaffold", "Create Windows WPF or macOS SwiftUI source template (opt-in; never overwrite)", {"name": "string", "template": "string"}),
]

def catalog():
    tools = []
    for name, description, fields in TOOL_SPECS:
        properties = {key: {"type": value} for key, value in fields.items()}
        required = (["query"] if name == "code.search" else
                    list(fields) if name in {"file.read", "file.replace", "browser.local_text", "browser.snapshot", "runtime.test", "project.scaffold"} else [])
        tools.append({"name": name, "description": description, "inputSchema": {
            "type": "object", "properties": properties, "required": required, "additionalProperties": False}})
    return tools

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
    if not allow_missing and not resolved.exists():
        raise FileNotFoundError(value)
    return resolved

def _text_file(path):
    if not path.is_file() or path.stat().st_size > MAX_TEXT:
        raise ValueError("File is not a regular small text file")
    return path.read_text(encoding="utf-8")

def _file_read(root, a):
    p = _path(root, a["path"])
    body = _text_file(p)
    return {"path": a["path"], "text": body,
            "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest()}

def _replace(root, a):
    if not isinstance(a["text"], str) or len(a["text"].encode("utf-8")) > MAX_TEXT:
        raise ValueError("Write exceeds UTF-8 file size limit")
    p = _path(root, a["path"], allow_missing=True)
    if not p.parent.is_dir():
        raise ValueError("Parent directory must already exist")
    expected = a["expectedSha256"]
    if not isinstance(expected, str):
        raise ValueError("expectedSha256 must be a string")
    if p.exists():
        if not p.is_file():
            raise ValueError("Target is not a regular file")
        previous = hashlib.sha256(p.read_bytes()).hexdigest()
        if previous != expected:
            raise ValueError("Conflict: current SHA-256 does not match expectedSha256")
    elif expected != "":
        raise ValueError("New file requires empty expectedSha256")
    temporary = None
    try:
        fd, temporary = tempfile.mkstemp(prefix=".aiws-", dir=p.parent)
        with os.fdopen(fd, "wb") as out:
            out.write(a["text"].encode("utf-8"))
            out.flush()
            os.fsync(out.fileno())
        os.chmod(temporary, p.stat().st_mode & 0o777 if p.exists() else 0o600)
        os.replace(temporary, p)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    return {"path": a["path"], "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "written": True}

def _tree(root, a):
    sub = _path(root, a.get("path", "."))
    if not sub.is_dir():
        raise ValueError("Expected directory")
    entries = []
    for base, dirs, names in os.walk(sub, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not (Path(base) / d).is_symlink())
        for name in sorted(names):
            candidate = Path(base) / name
            if candidate.is_symlink() or not candidate.is_file():
                continue
            entries.append(candidate.relative_to(root).as_posix())
            if len(entries) >= 300:
                return {"files": entries, "truncated": True}
    return {"files": entries, "truncated": False}

def _search(root, a):
    query = a["query"]
    if not isinstance(query, str) or not (1 <= len(query) <= 200):
        raise ValueError("Query must be literal text of 1-200 characters")
    folder = _path(root, a.get("path", "."))
    if not folder.is_dir():
        raise ValueError("Search path must be a directory")
    hits, scanned = [], 0
    for base, dirs, names in os.walk(folder, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not (Path(base) / d).is_symlink())
        for name in sorted(names):
            p = Path(base) / name
            if p.is_symlink() or not p.is_file() or p.stat().st_size > MAX_TEXT:
                continue
            scanned += 1
            if scanned > 400:
                return {"matches": hits, "scannedFiles": scanned - 1, "truncated": True}
            try:
                for number, line in enumerate(p.read_text("utf-8").splitlines(), 1):
                    if query in line:
                        hits.append({"path": p.relative_to(root).as_posix(), "line": number, "text": line[:240]})
                        if len(hits) >= 80:
                            return {"matches": hits, "scannedFiles": scanned, "truncated": True}
            except (UnicodeDecodeError, PermissionError, OSError):
                continue
    return {"matches": hits, "scannedFiles": scanned, "truncated": False}

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

def _git(root, a):
    if a.get("view", "status") not in ("status", "diff"):
        raise ValueError("Only git status and diff are available")
    if not shutil.which("git"):
        raise ValueError("Git not installed")
    args = ["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null",
            "-c", "diff.external=", "-c", "protocol.ext.allow=never"]
    if a.get("view", "status") == "status":
        args += ["status", "--short", "--untracked-files=normal"]
    else:
        args += ["diff", "--no-ext-diff", "--no-textconv", "--"]
    return _command(root, args)

LANGUAGES = {
    "python": ["python3", "-m", "unittest", "discover"],
    "node": ["npm", "test", "--if-present"],
    "go": ["go", "test", "./..."],
    "rust": ["cargo", "test", "--offline"],
    "java": ["mvn", "-o", "test"],
    "cpp": ["cmake", "--build", "build"],
}

def _runtime(root, a):
    if a.get("language") not in LANGUAGES:
        raise ValueError("Unrecognized language test profile")
    if os.environ.get("AIWS_ALLOW_EXEC") != "1":
        raise PermissionError("Execution disabled; owner must explicitly enable AIWS_ALLOW_EXEC=1 in guest session")
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        raise PermissionError("Agent test execution must not run as guest root")
    args = LANGUAGES[a["language"]]
    if not shutil.which(args[0]):
        raise FileNotFoundError("Tool not installed: " + args[0])
    return _command(root, args, timeout=90)

class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ignore = 0
        self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.ignore += 1
    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self.ignore:
            self.ignore -= 1
    def handle_data(self, data):
        if not self.ignore and data.strip():
            self.parts.append(data.strip())

def _extract(html):
    parser = _Text()
    parser.feed(html[:256000])
    return "\n".join(parser.parts)[:16000]

def _browser(root, a):
    url = a["url"]
    if not isinstance(url, str) or len(url) > 2048:
        raise ValueError("Invalid URL")
    parsed = urlsplit(url)
    if parsed.scheme not in ("https", "http") or parsed.username or parsed.password or not parsed.hostname:
        raise ValueError("Only explicitly allowlisted HTTP(S) origins are supported")
    origin = parsed.scheme + "://" + parsed.netloc.lower()
    allow = {x.strip().lower() for x in os.environ.get("AIWS_BROWSER_ALLOWED_ORIGINS", "").split(",") if x.strip()}
    if origin not in allow:
        raise PermissionError("Browser disabled for this origin; host network must be separately controlled")
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        raise PermissionError("Headless browser must run as an ordinary guest user with sandbox enabled")
    if not shutil.which("chromium") or not shutil.which("chromedriver"):
        raise FileNotFoundError("Debian chromium/chromium-driver are required")
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
    except ImportError as error:
        raise RuntimeError("Debian python3-selenium is required") from error
    options = Options()
    options.binary_location = shutil.which("chromium")
    options.add_argument("--headless=new")
    options.add_argument("--disable-extensions")
    options.add_argument("--no-first-run")
    options.add_argument("--disable-background-networking")
    with tempfile.TemporaryDirectory(prefix="aiws-browser-") as profile:
        options.add_argument("--user-data-dir=" + profile)
        service = Service(executable_path=shutil.which("chromedriver"), env=_safe_env())
        driver = webdriver.Chrome(service=service, options=options)
        try:
            driver.set_page_load_timeout(15)
            driver.get(url)
            final = urlsplit(driver.current_url)
            final_origin = final.scheme + "://" + final.netloc.lower()
            if final_origin not in allow:
                raise PermissionError("Redirected outside allowed origins; host egress rules are required")
            return {"url": driver.current_url, "title": driver.title[:300],
                    "text": _extract(driver.page_source), "source": "headless-chromium-dom"}
        finally:
            driver.quit()

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
    if name == "workspace.tree":
        return _tree(root, arguments)
    if name == "file.read":
        return _file_read(root, arguments)
    if name == "file.replace":
        return _replace(root, arguments)
    if name == "code.search":
        return _search(root, arguments)
    if name == "git.inspect":
        return _git(root, arguments)
    if name == "runtime.detect":
        return {"tools": {p: shutil.which(p) for p in
                ("python3", "node", "npm", "dotnet", "swift", "sourcekit-lsp", "xcodegen", "javac", "rustc", "cargo", "go",
                 "cc", "clang", "cmake", "mvn", "git", "chromium", "chromedriver")}}
    if name == "runtime.test":
        return _runtime(root, arguments)
    if name == "browser.local_text":
        return {"path": arguments["path"], "text": _extract(_text_file(_path(root, arguments["path"])))}
    if name == "browser.snapshot":
        return _browser(root, arguments)
    if name == "platform.inspect":
        return inspect_project(root, arguments.get("path", "."), _path)
    if name == "project.scaffold":
        return scaffold_project(root, arguments)
    raise AssertionError("Unreachable tool dispatch")

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
