"""`git.commit` for the cloud agent: stage and commit inside the project, nothing else. NOT a git shell.

There is no push, pull, fetch, remote, reset, rebase, checkout or clean here: a commit is local and recoverable (the old state is
still in the history). The project folder must be the ROOT of its own repository, so a commit can never sweep up files elsewhere.
Git runs hardened: no hooks, no system or global config, no editor, no signing, no external diff / fsmonitor / pager, no prompts.
"""
import os
import shutil
import subprocess
from pathlib import Path

from aiws_build_tool import BuildError, check_target

GIT = ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-c", "diff.external=", "-c", "core.pager=cat", "-c", "core.editor=true",
       "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", "-c", "protocol.ext.allow=never", "-c", "core.quotepath=false", "-c", "advice.detachedHead=false"]
MAX_MESSAGE = 500
MAX_PATHS = 20
DEFAULT_IDENTITY = ("AIWS Builder", "builder@aiws.local")


def _env(home):
    return {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": home, "LANG": "C.UTF-8", "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_OPTIONAL_LOCKS": "0"}


def _paths(project, paths):
    if paths in (None, []):
        return ["."]
    if not isinstance(paths, list) or len(paths) > MAX_PATHS:
        raise BuildError("paths must be a list of at most %d relative paths" % MAX_PATHS)
    out = []
    for p in paths:
        try:
            out.append(check_target(project, p)[0])
        except BuildError as exc:
            if "does not exist" not in str(exc):               # a deleted file is a legitimate thing to stage
                raise
            if not isinstance(p, str) or p.startswith("/") or ".." in Path(p).parts or p.startswith("-") or "\x00" in p:
                raise BuildError("Invalid path")
            out.append(p)
    return out


def plan_commit(args, project, which=shutil.which):
    """Validate and describe. Returns (command text for the approval prompt, steps)."""
    if not isinstance(args, dict) or set(args) - {"message", "paths"}:
        raise BuildError("Expected message and optionally paths")
    msg = args.get("message")
    if not isinstance(msg, str) or not 1 <= len(msg.strip()) <= MAX_MESSAGE or "\x00" in msg:
        raise BuildError("The commit message must be 1-%d characters" % MAX_MESSAGE)
    paths = _paths(project, args.get("paths"))
    exe = which("git")
    if not exe:
        raise BuildError("git is not installed on this system")
    first = msg.strip().splitlines()[0][:80]
    return 'git add -A -- %s && git commit -m "%s"' % (" ".join(paths), first), {"git": exe, "message": msg.strip(), "paths": paths}


def _run(argv, cwd, home, timeout=60):
    p = subprocess.run(argv, cwd=cwd, env=_env(home), stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout, shell=False)
    return p.returncode, (p.stdout + p.stderr).decode("utf-8", "replace")[:4000]


def commit(plan, project, home):
    """Run the plan. Returns text for the model (exit status first)."""
    git = [plan["git"]] + GIT[1:]
    cwd = str(project)
    code, out = _run(git + ["rev-parse", "--show-toplevel"], cwd, home)
    if code != 0:
        return "error: this project folder is not a git repository"
    if os.path.realpath(out.strip()) != os.path.realpath(cwd):
        return "error: the project folder must be the root of its own git repository (it is inside another one)"
    code, name = _run(git + ["config", "--get", "user.name"], cwd, home)
    ident = [] if code == 0 and name.strip() else ["-c", "user.name=" + DEFAULT_IDENTITY[0], "-c", "user.email=" + DEFAULT_IDENTITY[1]]
    code, out = _run(git + ["add", "-A", "--"] + plan["paths"], cwd, home)
    if code != 0:
        return "exit code %d\n%s" % (code, out)
    code, out = _run(git + ident + ["commit", "-m", plan["message"]], cwd, home)
    if code != 0:
        return ("nothing to commit (the working tree is clean)" if "nothing to commit" in out or "nothing added" in out else "exit code %d\n%s" % (code, out))
    code, log = _run(git + ["log", "-1", "--stat", "--format=%h %s"], cwd, home)
    return "committed: " + log.strip()[:1500]
