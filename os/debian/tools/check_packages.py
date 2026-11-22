#!/usr/bin/env python3
"""Check live-build package lists against a real Debian package index and estimate installed size.

Usage: check_packages.py PACKAGES_INDEX [LIST ...]
  PACKAGES_INDEX  path to Packages.xz (e.g. fetched from https://deb.debian.org/debian/dists/trixie/main/binary-amd64/Packages.xz)
Exit status is 1 if any listed package does not exist in the index. The size is an ESTIMATE (first alternative of each
Depends, virtual packages ignored); it is not what apt would compute exactly.
"""
import json
import lzma
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
LISTS = [HERE.parent / "config/package-lists/aiws-desktop.list.chroot", HERE.parent / "config/package-lists/aiws-devtools.list.chroot",
         HERE.parent / "optional/aiws-swift.list.chroot"]

def read_list(path):
    return [l.split("#")[0].strip() for l in Path(path).read_text(encoding="utf-8").splitlines() if l.split("#")[0].strip()]

def load_index(path):
    index = {}
    for block in lzma.open(path, "rt", encoding="utf-8").read().split("\n\n"):
        fields = {}
        for line in block.split("\n"):
            if not line.startswith(" ") and ":" in line:
                key, value = line.split(":", 1)
                fields[key] = value.strip()
        if "Package" in fields:
            index[fields["Package"]] = fields
    return index

def closure(index, names):
    seen, stack = set(), list(names)
    while stack:
        name = stack.pop()
        if name in seen or name not in index:
            continue
        seen.add(name)
        for field in ("Depends", "Pre-Depends"):
            for part in index[name].get(field, "").split(","):
                dep = re.split(r"[ (:\[]", part.split("|")[0].strip())[0]
                if dep in index:
                    stack.append(dep)
    return seen

def main(argv):
    index = load_index(argv[1])
    lists = [Path(p) for p in argv[2:]] or LISTS
    names = [n for p in lists for n in read_list(p)]
    missing = sorted({n for n in names if n not in index})
    base = closure(index, read_list(lists[0]))
    everything = closure(index, names)
    size = lambda s: sum(int(index[x].get("Installed-Size", "0")) for x in s) / 1024
    print(json.dumps({"packages": len(names), "missing": missing, "estimatedInstalledMB": round(size(everything)),
                      "estimatedAddedByLaterListsMB": round(size(everything - base))}, indent=2))
    return 1 if missing else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv) if len(sys.argv) > 1 else print(__doc__) or 2)
