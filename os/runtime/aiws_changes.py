"""Read-only change review for a project folder: which files changed, how much, and the diff of one file.

This is the "what did the AI actually do" view. It only ever runs `git status` / `git diff` with hardening flags
(no hooks, no external diff drivers, no textconv, no fsmonitor, no pager), inside a project folder confined by the
tool plane's own path rules (no absolute paths, `..`, symlinks, `.git`, `.ssh`). Output is bounded.
"""
import re
import shutil
import subprocess

import aiws_toolplane as tp

MAX_FILES = 300
MAX_DIFF = 60000
GIT = ["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-c", "diff.external=",
       "-c", "protocol.ext.allow=never", "-c", "core.pager=cat", "-c", "core.quotepath=false"]
STATUS_NAME = {"M": "modified", "A": "added", "D": "deleted", "R": "renamed", "C": "copied", "?": "untracked", "U": "conflict"}


class ChangesError(Exception):
    """Safe-to-show rejection."""


def _run(project, args, limit):
    if not shutil.which("git"):
        raise ChangesError("Git is not installed")
    try:
        p = subprocess.run(GIT + args, cwd=project, env=tp._safe_env(), capture_output=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise ChangesError("Git did not answer")
    return p.returncode, p.stdout[:limit].decode("utf-8", "replace"), p.stdout.__len__() > limit


def project_dir(root, rel):
    try:
        path = tp._path(root, rel or ".")
    except (ValueError, FileNotFoundError, PermissionError) as exc:
        raise ChangesError(str(exc)[:120])
    if not path.is_dir():
        raise ChangesError("Not a folder")
    return path


def parse_status(text):
    """`git status --porcelain=v1 -z` -> [{path, status, staged}]. Renames carry their old path in `from`."""
    rows, parts, i = [], text.split("\0"), 0
    while i < len(parts):
        entry = parts[i]
        i += 1
        if len(entry) < 4:
            continue
        x, y, path = entry[0], entry[1], entry[3:]
        row = {"path": path, "status": STATUS_NAME.get(y if y not in " " else x, "modified"), "staged": x not in " ?"}
        if x in "RC":                              # next NUL field is the source path
            row["from"] = parts[i] if i < len(parts) else ""
            i += 1
        rows.append(row)
    return rows


def parse_numstat(text):
    out = {}
    for line in text.splitlines():
        m = re.match(r"^(\d+|-)\t(\d+|-)\t(.+)$", line)
        if m:
            out[m.group(3)] = {"added": None if m.group(1) == "-" else int(m.group(1)),
                               "removed": None if m.group(2) == "-" else int(m.group(2))}
    return out


def changes(root, rel):
    project = project_dir(root, rel)
    code, out, cut = _run(project, ["status", "--porcelain=v1", "-z", "--untracked-files=normal"], 200000)
    if code != 0:
        raise ChangesError("Not a git project (nothing to compare against)")
    files = parse_status(out)[:MAX_FILES]
    code, num, _ = _run(project, ["diff", "--numstat", "--no-ext-diff", "--no-textconv", "HEAD", "--"], 200000)
    stats = parse_numstat(num) if code == 0 else {}
    for f in files:
        f.update(stats.get(f["path"], {"added": None, "removed": None}))
    return {"project": rel or ".", "files": files, "truncated": cut or len(files) >= MAX_FILES}


def diff(root, rel, file):
    project = project_dir(root, rel)
    try:
        target = tp._path(project, file, allow_missing=True)      # same confinement for the file inside the project
    except (ValueError, PermissionError) as exc:
        raise ChangesError(str(exc)[:120])
    name = str(target.relative_to(project))
    code, out, cut = _run(project, ["diff", "--no-ext-diff", "--no-textconv", "--no-color", "HEAD", "--", name], MAX_DIFF)
    if code != 0:
        raise ChangesError("No diff available")
    if not out and target.is_file():                              # untracked: show it as an all-added diff, size-capped
        try:
            body = target.read_bytes()[:MAX_DIFF]
        except OSError:
            raise ChangesError("Unreadable file")
        if b"\0" in body:
            return {"file": name, "diff": "", "binary": True, "truncated": False}
        text = body.decode("utf-8", "replace")
        return {"file": name, "diff": "".join("+" + l + "\n" for l in text.splitlines()), "binary": False, "truncated": target.stat().st_size > MAX_DIFF}
    return {"file": name, "diff": out, "binary": False, "truncated": cut}
