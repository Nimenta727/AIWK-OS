"""Integrated applications and tools of the AIWS workbench: one registry, three kinds.

  builtin  tabs rendered by the workbench itself (file viewer, preview browser, AI file manager ...)
  gui      desktop programs the workbench can start. The command is FIXED here: no argument, URL or path from a request
           is ever appended, and the environment handed to the child is an allowlist (never the service's own).
  cli      command-line tools that are detected and reported (the AI calls them through the audited tool plane).

The registry is data, so the UI, the local model (`tools.list`) and the tests all read the same list. Nothing here
executes anything except `launch()` for `gui` entries, and only after the HTTP layer has checked CSRF and rate limits.
"""
import os
import shutil
import subprocess
import time

# id, kind, category, zh, en, executables (any one found = installed), launch argv (gui only)
REGISTRY = (
    ("viewer",   "builtin", "read",    "文档阅读器",   "Document reader",   (), None),
    ("browser",  "builtin", "web",     "内置浏览器",   "Preview browser",   (), None),
    ("files",    "builtin", "files",   "AI 文件管理",  "AI file manager",   (), None),
    ("aiws-code", "gui",    "code",    "AIWS Code 编辑器", "AIWS Code editor", ("aiws-code",), ("aiws-code",)),
    ("terminal", "gui",     "code",    "终端",         "Terminal",          ("xfce4-terminal",), ("xfce4-terminal",)),
    ("chromium", "gui",     "web",     "Chromium 浏览器", "Chromium browser", ("chromium",), ("chromium",)),
    ("firefox",  "gui",     "web",     "Firefox 浏览器", "Firefox browser", ("firefox-esr", "firefox"), ("firefox-esr",)),
    ("files-gui", "gui",    "files",   "文件管理器",   "File manager",      ("thunar",), ("thunar",)),
    ("editor",   "gui",     "code",    "轻量编辑器",   "Light editor",      ("geany", "mousepad"), ("geany",)),
    ("btop",     "cli",     "system",  "资源监视 btop", "btop monitor",     ("btop",), None),
    ("git",      "cli",     "vcs",     "Git",          "Git",               ("git",), None),
    ("gh",       "cli",     "vcs",     "GitHub CLI",   "GitHub CLI",        ("gh",), None),
    ("rg",       "cli",     "search",  "ripgrep 搜索", "ripgrep search",    ("rg",), None),
    ("jq",       "cli",     "data",    "jq JSON 处理", "jq JSON",           ("jq",), None),
    ("sqlite",   "cli",     "data",    "SQLite",       "SQLite",            ("sqlite3",), None),
    ("pdftotext", "cli",    "read",    "PDF 文本提取 (poppler)", "PDF text (poppler)", ("pdftotext",), None),
    ("pandoc",   "cli",     "read",    "Pandoc 文档转换", "Pandoc converter", ("pandoc",), None),
)
IDS = frozenset(r[0] for r in REGISTRY)
LAUNCH_ENV = ("HOME", "PATH", "LANG", "DISPLAY", "XAUTHORITY", "XDG_RUNTIME_DIR", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS")
RATE_SECONDS = 2.0
_last_launch = {}

def _found(executables, which):
    for name in executables:
        path = which(name)
        if path:
            return path
    return None

def listing(which=None):
    """Registry rows with `installed` (and the resolved executable path for gui/cli). Builtins are always available."""
    which = which or shutil.which
    rows = []
    for ident, kind, category, zh, en, executables, launch in REGISTRY:
        path = _found(executables, which) if executables else None
        rows.append({"id": ident, "kind": kind, "category": category, "zh": zh, "en": en,
                     "installed": True if kind == "builtin" else path is not None,
                     "path": path, "launchable": kind == "gui" and launch is not None and path is not None})
    return rows

def launch(ident, workspace, which=None, popen=None, clock=time.monotonic):
    """Start one registered gui program. Returns {"started": bool}. Raises ValueError/FileNotFoundError."""
    which, popen = which or shutil.which, popen or subprocess.Popen
    if not isinstance(ident, str) or ident not in IDS:
        raise ValueError("Unknown application")
    entry = next(r for r in REGISTRY if r[0] == ident)
    if entry[1] != "gui" or entry[6] is None:
        raise ValueError("This entry cannot be launched from outside the workbench")
    path = _found(entry[5], which)
    if not path:
        raise FileNotFoundError("Not installed in this image: " + entry[4])
    now = clock()
    if now - _last_launch.get(ident, -1e9) < RATE_SECONDS:
        return {"started": False, "starting": True}
    _last_launch[ident] = now
    env = {k: os.environ[k] for k in LAUNCH_ENV if k in os.environ}
    env["AIWS_WORKSPACE"] = str(workspace)
    argv = [path] + list(entry[6][1:])                       # fixed command line; nothing from the request
    popen(argv, cwd=str(workspace), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
          start_new_session=True, close_fds=True, shell=False, env=env)
    return {"started": True, "running": False}
