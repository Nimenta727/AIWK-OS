"""Guest file tools of the tool plane: read, edit, copy/move/trash/restore, tree, search, logs, documents.

Every path goes through aiws_toolplane._path (workspace containment, no symlinks, no .git/.ssh).
Dispatched by aiws_toolplane.invoke; not called directly from outside the plane.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from aiws_tools_system import _extract
from aiws_toolplane import (MAX_TEXT, SKIP_DIRS, TRASH, MAX_COPY_BYTES, MAX_TREE_ENTRIES, MAX_TRASH_ITEMS,
                            DOC_MAX_BYTES, DOC_TEXT_LIMIT, PANDOC_SUFFIXES, _path, _text_file, _safe_env)


def _file_read(root, a):
    p = _path(root, a["path"])
    body = _text_file(p)
    return {"path": a["path"], "text": body,
            "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest()}

def _log_digest(root, a):
    import aiws_logdigest
    try:
        result = aiws_logdigest.digest_file(_path(root, a["path"]))
    except aiws_logdigest.LogError as exc:
        raise ValueError(str(exc))
    return {"path": a["path"], **result}

def _log_lines(root, a):
    import aiws_logdigest
    try:
        result = aiws_logdigest.line_range(_path(root, a["path"]), a["start"], a["end"])
    except aiws_logdigest.LogError as exc:
        raise ValueError(str(exc))
    return {"path": a["path"], **result}

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

def _doc_text(root, a):
    """Text of a workspace document. Only fixed argv lists; output bounded; the file never leaves the workspace."""
    path = _path(root, a["path"])
    if not path.is_file():
        raise ValueError("Not a regular file")
    size = path.stat().st_size
    if size > DOC_MAX_BYTES:
        raise ValueError("Document is larger than 32 MiB")
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        exe, argv, source = shutil.which("pdftotext"), None, "pdftotext"
        if not exe:
            raise FileNotFoundError("poppler-utils (pdftotext) is not installed")
        argv = [exe, "-q", "-layout", "-l", "60", str(path), "-"]
    elif suffix in PANDOC_SUFFIXES:
        exe, source = shutil.which("pandoc"), "pandoc"
        if not exe:
            raise FileNotFoundError("pandoc is not installed")
        argv = [exe, "--sandbox", "-f", PANDOC_SUFFIXES[suffix], "-t", "plain", "--wrap=none", str(path)]
    elif suffix in (".html", ".htm"):
        text, source = _extract(_text_file(path)), "html"
        return {"path": a["path"], "source": source, "text": text, "truncated": False, "bytes": size}
    else:
        text = _text_file(path)
        return {"path": a["path"], "source": "text", "text": text[:DOC_TEXT_LIMIT],
                "truncated": len(text) > DOC_TEXT_LIMIT, "bytes": size}
    result = subprocess.run(argv, cwd=root, env=_safe_env(), capture_output=True, text=True, errors="replace",
                            timeout=30, check=False)
    if result.returncode != 0:
        raise ValueError("The converter could not read this document")
    return {"path": a["path"], "source": source, "text": result.stdout[:DOC_TEXT_LIMIT],
            "truncated": len(result.stdout) > DOC_TEXT_LIMIT, "bytes": size}
