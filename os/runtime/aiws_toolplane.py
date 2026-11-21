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
import re
import tempfile
import uuid
from aiws_crossplatform import inspect_project, scaffold_project
from aiws_guest_boundary import protect_guest_workspace
from aiws_codeintel import symbols as code_symbols, references as code_references, dependencies as code_dependencies, platform_apis as code_platform_apis
import time
from urllib.parse import urlsplit

MAX_TEXT = 128 * 1024
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "target", "dist", "build", ".aiws-trash"}
TRASH = ".aiws-trash"
MAX_COPY_BYTES = 64 * 1024 * 1024
MAX_TREE_ENTRIES = 5000
MAX_TRASH_ITEMS = 500
TOOL_SPECS = [
    ("workspace.tree", "List bounded workspace files without following symlinks", {"path": "string"}),
    ("file.read", "Read a UTF-8 file and its SHA-256", {"path": "string"}),
    ("file.stat", "Read type, size, mtime and SHA-256 (directories: bounded tree fingerprint)", {"path": "string"}),
    ("file.trashList", "List items in the reversible workspace trash (id, original path, type, time)", {}),
    ("file.mkdir", "Create one new directory; parent must exist; guest workspace write", {"path": "string"}),
    ("file.copy", "Copy one regular file (<=64MiB) to a new path; never overwrites; guest workspace write", {"path": "string", "to": "string", "expectedSha256": "string"}),
    ("file.move", "Move or rename a file or directory to a new path; never overwrites; fingerprint precondition", {"path": "string", "to": "string", "expectedSha256": "string"}),
    ("file.trash", "Move a file or directory to the reversible workspace trash; never deletes permanently", {"path": "string", "expectedSha256": "string"}),
    ("file.restore", "Restore a trashed item to its original path if still free", {"trashId": "string"}),
    ("file.replace", "Atomically replace a file with SHA-256 precondition; guest workspace write", {"path": "string", "text": "string", "expectedSha256": "string"}),
    ("code.search", "Search literal text in source files with bounded output", {"query": "string", "path": "string"}),
    ("git.inspect", "Read git status or diff (not commit/push)", {"view": "string"}),
    ("runtime.detect", "Discover installed language and build executables", {}),
    ("runtime.test", "Execute a fixed language test command in the guest workspace; opt-in", {"language": "string"}),
    ("browser.local_text", "Extract text from an HTML document in the workspace", {"path": "string"}),
    ("browser.snapshot", "Headless Chromium DOM-text snapshot; disabled until exact origins are configured", {"url": "string"}),
    ("platform.inspect", "Recognize Windows/macOS/Swift project sources without building", {"path": "string"}),
    ("project.scaffold", "Create Windows WPF or macOS SwiftUI source template (opt-in; never overwrite)", {"name": "string", "template": "string"}),
    ("code.symbols", "Read-only C#/Swift source symbol index; syntax-level candidates", {"path": "string", "query": "string"}),
    ("code.references", "Find symbol definitions and unresolved cross-file identifier occurrences", {"symbol": "string", "path": "string"}),
    ("code.dependencies", "Inspect MSBuild/NuGet, SwiftPM and XcodeGen declared dependencies without build", {"path": "string"}),
    ("code.platformApis", "Find WPF/WinUI/interop and SwiftUI/AppKit/UIKit API usage evidence", {"path": "string"}),
]

def catalog():
    tools = []
    for name, description, fields in TOOL_SPECS:
        properties = {key: {"type": value} for key, value in fields.items()}
        required = (["query"] if name == "code.search" else
                    ["symbol"] if name == "code.references" else
                    list(fields) if name in {"file.read", "file.replace", "file.stat", "file.mkdir", "file.copy", "file.move", "file.trash", "file.restore", "browser.local_text", "browser.snapshot", "runtime.test", "project.scaffold"} else [])
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

def _sha_file(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def _fingerprint(path):
    """SHA-256 of a regular file, or a bounded deterministic digest of a directory tree.

    Directories containing symlinks or special files are refused so that a
    precondition always describes exactly what a move/trash will carry along.
    """
    if path.is_symlink():
        raise ValueError("Symlinks are not supported")
    if path.is_file():
        return "file", _sha_file(path)
    if not path.is_dir():
        raise ValueError("Only regular files and directories are supported")
    h, count = hashlib.sha256(), 0
    for base, dirs, names in os.walk(path, followlinks=False):
        dirs.sort()
        for name in sorted(names + dirs):
            item = Path(base) / name
            count += 1
            if count > MAX_TREE_ENTRIES:
                raise ValueError("Directory has too many entries for a tracked operation")
            rel = item.relative_to(path).as_posix()
            if item.is_symlink():
                raise ValueError("Directory contains a symlink; operation refused")
            if item.is_dir():
                h.update(b"D\0" + rel.encode("utf-8") + b"\0")
            elif item.is_file():
                h.update(b"F\0" + rel.encode("utf-8") + b"\0" + _sha_file(item).encode() + b"\0")
            else:
                raise ValueError("Directory contains a special file; operation refused")
    return "dir", h.hexdigest()

def _trash_list(root, a):
    bin_ = root / TRASH
    items = []
    if bin_.is_dir() and not bin_.is_symlink():
        for slot in sorted(bin_.iterdir()):
            meta = slot / "meta.json"
            if (slot.is_symlink() or not re.fullmatch("[a-f0-9]{32}", slot.name)
                    or meta.is_symlink() or not meta.is_file()):
                continue
            try:
                m = json.loads(meta.read_text(encoding="utf-8"))
                items.append({"trashId": slot.name, "original": str(m["original"])[:512],
                              "type": str(m["type"]), "trashedAt": int(m["trashedAt"])})
            except (ValueError, KeyError, TypeError):
                continue
            if len(items) >= MAX_TRASH_ITEMS:
                break
    return {"items": items}

def _guard_ops_path(value):
    if Path(value).parts[:1] == (TRASH,):
        raise ValueError("The workspace trash is managed only by file.trash/file.restore")

def _source(root, a):
    _guard_ops_path(a["path"])
    src = _path(root, a["path"])
    if src == root:
        raise ValueError("The workspace root cannot be moved or trashed")
    kind, digest = _fingerprint(src)
    expected = a.get("expectedSha256")
    if not isinstance(expected, str) or expected != digest:
        raise ValueError("Conflict: current fingerprint does not match expectedSha256")
    return src, kind, digest

def _destination(root, value):
    _guard_ops_path(value)
    dst = _path(root, value, allow_missing=True)
    if dst == root or os.path.lexists(dst):
        raise ValueError("Destination already exists; overwriting is not allowed")
    if not dst.parent.is_dir() or dst.parent.is_symlink():
        raise ValueError("Destination parent directory must already exist")
    return dst

def _stat(root, a):
    _guard_ops_path(a["path"])
    p = _path(root, a["path"])
    kind, digest = _fingerprint(p)
    st = p.stat()
    return {"path": a["path"], "type": kind, "size": st.st_size if kind == "file" else None,
            "mtime": int(st.st_mtime), "sha256": digest}

def _mkdir(root, a):
    _guard_ops_path(a["path"])
    p = _path(root, a["path"], allow_missing=True)
    if p == root or os.path.lexists(p):
        raise ValueError("Path already exists")
    if not p.parent.is_dir() or p.parent.is_symlink():
        raise ValueError("Parent directory must already exist")
    os.mkdir(p, 0o755)
    return {"path": a["path"], "created": True}

def _copy(root, a):
    src, kind, digest = _source(root, a)
    if kind != "file" or src.stat().st_size > MAX_COPY_BYTES:
        raise ValueError("Only regular files up to 64MiB can be copied")
    dst = _destination(root, a["to"])
    temporary = None
    try:
        fd, temporary = tempfile.mkstemp(prefix=".aiws-", dir=dst.parent)
        with os.fdopen(fd, "wb") as out, src.open("rb") as inp:
            shutil.copyfileobj(inp, out, length=1024 * 1024)
            out.flush()
            os.fsync(out.fileno())
        os.chmod(temporary, src.stat().st_mode & 0o777)
        if _sha_file(Path(temporary)) != digest:
            raise ValueError("Source changed while copying")
        os.link(temporary, dst)  # fails if the destination appeared meanwhile
    finally:
        if temporary and os.path.lexists(temporary):
            os.unlink(temporary)
    return {"path": a["path"], "to": a["to"], "sha256": digest, "copied": True}

def _move_nofollow(src, dst, kind):
    if kind == "file":
        os.link(src, dst)  # atomic, refuses to replace an existing path
        os.unlink(src)
    else:
        if dst.is_relative_to(src):
            raise ValueError("Cannot move a directory into itself")
        os.rename(src, dst)

def _move(root, a):
    src, kind, digest = _source(root, a)
    dst = _destination(root, a["to"])
    _move_nofollow(src, dst, kind)
    return {"path": a["path"], "to": a["to"], "type": kind, "sha256": digest, "moved": True}

def _trash_dir(root):
    d = root / TRASH
    if d.is_symlink():
        raise ValueError("Workspace trash must not be a symlink")
    d.mkdir(mode=0o700, exist_ok=True)
    return d

def _trash(root, a):
    src, kind, digest = _source(root, a)
    bin_ = _trash_dir(root)
    if sum(1 for _ in bin_.iterdir()) >= MAX_TRASH_ITEMS:
        raise ValueError("Workspace trash is full; restore or review items first")
    ident = uuid.uuid4().hex
    slot = bin_ / ident
    slot.mkdir(mode=0o700)
    _move_nofollow(src, slot / "payload", kind)
    meta = {"original": a["path"], "type": kind, "sha256": digest, "trashedAt": int(time.time())}
    (slot / "meta.json").write_text(json.dumps(meta, sort_keys=True), encoding="utf-8")
    return {"path": a["path"], "trashId": ident, "type": kind, "sha256": digest, "trashed": True}

def _restore(root, a):
    ident = a["trashId"]
    if not isinstance(ident, str) or not re.fullmatch("[a-f0-9]{32}", ident):
        raise ValueError("Invalid trash id")
    slot = root / TRASH / ident
    if (root / TRASH).is_symlink() or slot.is_symlink() or not slot.is_dir():
        raise ValueError("Unknown trash item")
    meta_file, payload = slot / "meta.json", slot / "payload"
    if meta_file.is_symlink() or not meta_file.is_file():
        raise ValueError("Trash metadata missing")
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        original, kind, digest = meta["original"], meta["type"], meta["sha256"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError("Trash metadata damaged") from exc
    got_kind, got_digest = _fingerprint(payload)
    if (got_kind, got_digest) != (kind, digest):
        raise ValueError("Trashed content no longer matches its recorded fingerprint")
    dst = _destination(root, original)
    _move_nofollow(payload, dst, kind)
    meta_file.unlink()
    slot.rmdir()
    return {"path": original, "trashId": ident, "type": kind, "sha256": digest, "restored": True}

def _tree(root, a):
    sub = _path(root, a.get("path", "."))
    if not sub.is_dir():
        raise ValueError("Expected directory")
    entries, folders = [], []
    for base, dirs, names in os.walk(sub, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not (Path(base) / d).is_symlink())
        for d in dirs:
            if len(folders) < 300:
                folders.append((Path(base) / d).relative_to(root).as_posix())
        for name in sorted(names):
            candidate = Path(base) / name
            if candidate.is_symlink() or not candidate.is_file():
                continue
            entries.append(candidate.relative_to(root).as_posix())
            if len(entries) >= 300:
                return {"files": entries, "dirs": folders, "truncated": True}
    return {"files": entries, "dirs": folders, "truncated": False}

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
    handler = {"file.stat": _stat, "file.trashList": _trash_list, "file.mkdir": _mkdir, "file.copy": _copy,
               "file.move": _move, "file.trash": _trash, "file.restore": _restore}.get(name)
    if handler is not None:
        return handler(root, arguments)
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
    if name == "code.symbols":
        return code_symbols(root, arguments, _path)
    if name == "code.references":
        return code_references(root, arguments, _path)
    if name == "code.dependencies":
        return code_dependencies(root, arguments, _path)
    if name == "code.platformApis":
        return code_platform_apis(root, arguments, _path)
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
