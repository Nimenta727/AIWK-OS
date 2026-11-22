#!/usr/bin/env python3
"""Check the AIWS system files against the manifest written at image build time.

The live system's root is a read-only squashfs, but live-boot puts a writable overlay on top, so a modified file would otherwise
go unnoticed. This module compares sha256 digests of every file listed in the manifest and reports modified, missing and
UNLISTED files under the guarded directories. Run at boot (before the workbench starts) and on demand; the result is a small
JSON file the workbench shows as a banner. It reports; it never repairs or deletes anything.
"""
import hashlib
import json
import os
import sys
from pathlib import Path

# Every file the image ships under these is hashed (modified / missing are reported) ...
GUARDED = ("/usr/local/lib/aiws", "/usr/local/share/aiws", "/usr/local/bin", "/etc/systemd/user", "/etc/systemd/system", "/etc/sudoers.d", "/etc/aiws")
# ... but an UNLISTED file is only suspicious where the image is the sole writer. /usr/local/bin and /etc/systemd/system are
# excluded on purpose (as is /etc/sudoers.d, where live-config adds its own file): they would be false alarms.
STRICT = ("/usr/local/lib/aiws", "/usr/local/share/aiws", "/etc/aiws", "/etc/systemd/user")
SKIP_DIRS = ("/usr/local/share/aiws/model-preload",)     # multi-GB model weights are verified by their own checksum gate
MANIFEST = "/usr/local/share/aiws/system.sha256.json"
RESULT = "/run/aiws/system-verify.json"
SKIP_SUFFIX = (".pyc",)
MAX_FILES = 20000


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def walk(roots, prefix=""):
    n = 0
    skip = tuple(prefix + d for d in SKIP_DIRS)
    for root in roots:
        for base, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = [d for d in dirs if d != "__pycache__" and os.path.join(base, d) not in skip]
            for f in files:
                p = os.path.join(base, f)
                if p.endswith(SKIP_SUFFIX) or p == prefix + MANIFEST:
                    continue
                n += 1
                if n > MAX_FILES:
                    return
                yield p


def build_manifest(roots, prefix=""):
    """Manifest for a tree (prefix is stripped, used when building from a staging directory)."""
    out = {}
    for p in walk([prefix + r for r in roots if os.path.isdir(prefix + r)], prefix):
        if os.path.islink(p):
            out["link:" + p[len(prefix):]] = os.readlink(p)
        else:
            out[p[len(prefix):]] = digest(p)
    return out


def verify(manifest, strict_roots=STRICT, prefix=""):
    modified, missing = [], []
    for path, want in manifest.items():
        real = prefix + (path[5:] if path.startswith("link:") else path)
        if path.startswith("link:"):
            if not os.path.islink(real) or os.readlink(real) != want:
                modified.append(path[5:])
        elif not os.path.isfile(real):
            missing.append(path)
        elif os.path.islink(real) or digest(real) != want:
            modified.append(path)
    now = build_manifest(strict_roots, prefix)
    unlisted = sorted(set(now) - set(manifest))
    return {"ok": not (modified or missing or unlisted), "modified": sorted(modified)[:50], "missing": sorted(missing)[:50],
            "unlisted": unlisted[:50], "checked": len(manifest)}


def main(argv=None):
    argv = argv or sys.argv[1:]
    if argv[:1] == ["build"] and len(argv) in (2, 3):
        prefix = argv[2] if len(argv) == 3 else ""
        Path(argv[1]).write_text(json.dumps(build_manifest(GUARDED, prefix), sort_keys=True, indent=0) + "\n", encoding="utf-8")
        return 0
    try:
        manifest = json.loads(Path(MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        result = {"ok": False, "modified": [], "missing": [], "unlisted": [], "checked": 0, "error": "manifest missing or unreadable"}
    else:
        result = verify(manifest)
    try:
        Path(RESULT).parent.mkdir(parents=True, exist_ok=True)
        Path(RESULT).write_text(json.dumps(result), encoding="utf-8")
    except OSError:
        pass
    print(json.dumps(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
