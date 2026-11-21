"""Declarative external tools: read-only commands the AI may call (and the Agent audits) without a shell.

Every tool is data: parameters with a kind (text / path / int), limits, and a FIXED argv template. Values are substituted
as single argv elements AFTER a `--` where the program supports it, so a value can never become an option. Paths are
confined by the tool plane's own `_path` (no absolute paths, `..`, symlinks, `.git`, `.ssh`). Output and time are bounded
and the child gets a scrubbed environment. Nothing here can write: write/launch classes go through approval stages
(see aiws_launcher.py and aiws_tasks.WRITE_TOOLS).

sqlite is NOT run through the `sqlite3` shell (its `writefile()`/dot-commands can write files even with -readonly):
it uses Python's sqlite3 with a read-only URI and an authorizer that only permits SELECT.
"""
import json
import re
import shutil
import sqlite3
import subprocess

OUT_LIMIT = 24000
TIMEOUT = 20

# name -> (description, params, exe, argv template or None for native)
#   params: {name: (kind, required, max)}; kind in text | path | int | file
EXT = {
    "ext.rg": ("Search file contents with ripgrep (regex, bounded output, no config, no symlinks)",
               {"pattern": ("text", True, 256), "path": ("path", False, 512)},
               "rg", ["--no-config", "--no-follow", "--line-number", "--no-heading", "--color", "never",
                      "--max-count", "20", "--max-columns", "200", "--max-filesize", "1M", "--threads", "1",
                      "--glob", "!.git", "--glob", "!.aiws-trash", "-e", "{pattern}", "--", "{path}"]),
    "ext.jq": ("Run a jq filter over one JSON file in the workspace (read-only, compact output)",
               {"filter": ("text", True, 512), "path": ("file", True, 512)},
               "jq", ["--compact-output", "--", "{filter}", "{path}"]),
    "ext.gitlog": ("Show recent git commits (oneline, bounded), optionally for one path",
                   {"count": ("int", False, 50), "path": ("path", False, 512)},
                   "git", ["-c", "core.pager=cat", "-c", "core.fsmonitor=false", "--no-pager", "log", "--no-color",
                           "--oneline", "--max-count", "{count}", "--", "{path}"]),
    "ext.sqlite": ("Run ONE read-only SELECT against a SQLite file in the workspace (max 100 rows)",
                   {"path": ("file", True, 512), "query": ("text", True, 2000)}, None, None),
}
FORBIDDEN_TEXT = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

class ExtToolError(ValueError):
    pass

def names():
    return frozenset(EXT)

def specs():
    """(name, description, {param: 'string'}) triples for the tool catalog; required is derived by `required()`."""
    return [(n, d, {p: "string" for p in params}) for n, (d, params, _e, _a) in EXT.items()]

def required(name):
    return [p for p, (_k, req, _m) in EXT[name][1].items() if req]

def _validate(name, args, root, path_fn):
    desc, params, _exe, _argv = EXT[name]
    if not isinstance(args, dict) or set(args) - set(params):
        raise ExtToolError("Unexpected argument")
    out = {}
    for pname, (kind, req, limit) in params.items():
        if pname not in args:
            if req:
                raise ExtToolError("Missing argument: " + pname)
            continue
        value = args[pname]
        cap = 512 if kind in ("path", "file") else (limit if kind == "text" else 8)
        if not isinstance(value, str) or not value or len(value) > cap:
            raise ExtToolError("Invalid argument: " + pname)
        if FORBIDDEN_TEXT.search(value):
            raise ExtToolError("Control characters are not allowed")
        if kind == "int":
            if not value.isdigit() or not 1 <= int(value) <= limit:
                raise ExtToolError("%s must be an integer 1-%d" % (pname, limit))
        elif kind in ("path", "file"):
            resolved = path_fn(root, value)
            if kind == "file" and not resolved.is_file():
                raise ExtToolError("Not a regular file: " + pname)
            value = resolved.relative_to(root).as_posix() or "."
        out[pname] = value
    return out

def _run_argv(root, name, values, which, run, env):
    _d, params, exe, template = EXT[name]
    program = which(exe)
    if not program:
        raise FileNotFoundError(exe + " is not installed in this image")
    defaults = {"path": ".", "count": "20"}
    argv = [program]
    for part in template:
        if part.startswith("{") and part.endswith("}"):
            key = part[1:-1]
            value = values.get(key, defaults.get(key))
            if value is None:
                continue
            argv.append(value)
        else:
            argv.append(part)
    if name == "ext.jq" and values["filter"].startswith("-"):
        raise ExtToolError("A jq filter cannot start with '-'")
    if name == "ext.gitlog" and "path" not in values:
        argv = argv[:-2]                                   # no pathspec: drop the "--" and the placeholder
    result = run(argv, cwd=str(root), env=env, capture_output=True, text=True, errors="replace",
                 timeout=TIMEOUT, check=False)
    return {"tool": name, "exitCode": result.returncode, "stdout": result.stdout[:OUT_LIMIT],
            "stderr": result.stderr[:4000], "truncated": len(result.stdout) > OUT_LIMIT}

def _sqlite(root, values):
    query = values["query"].strip().rstrip(";").strip()
    if ";" in query or not re.match(r"(?is)^(select|with)\b", query):
        raise ExtToolError("Exactly one SELECT statement is allowed")
    target = (root / values["path"]).resolve()
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}

    def authorizer(action, *_):
        return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY

    try:
        conn = sqlite3.connect("file:" + str(target) + "?mode=ro", uri=True, timeout=2)
    except sqlite3.Error as exc:
        raise ExtToolError("Cannot open the database read-only") from exc
    try:
        conn.set_authorizer(authorizer)
        # mode=ro already makes the file read-only; the authorizer additionally denies every non-SELECT action
        cursor = conn.execute(query)
        columns = [c[0] for c in cursor.description or []]
        rows = [list(r) for r in cursor.fetchmany(100)]
        extra = cursor.fetchone() is not None
    except sqlite3.Error as exc:
        raise ExtToolError("Query rejected: " + str(exc)[:160]) from exc
    finally:
        conn.close()
    safe = json.loads(json.dumps({"columns": columns, "rows": rows}, default=lambda b: "<%d bytes>" % len(b) if isinstance(b, bytes) else str(b)))
    return {"tool": "ext.sqlite", **safe, "truncated": extra}

def run(name, args, root, path_fn, env, which=None, runner=None):
    """Validate and run one external tool. `path_fn` is the tool plane's confinement (root, value) -> resolved Path."""
    if name not in EXT:
        raise ExtToolError("Unknown external tool")
    values = _validate(name, args, root, path_fn)
    if name == "ext.sqlite":
        return _sqlite(root, values)
    return _run_argv(root, name, values, which or shutil.which, runner or subprocess.run, env)
