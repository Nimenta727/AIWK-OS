#!/usr/bin/env python3
"""Write manifest.json (name -> sha256) for the skills in a directory. The runtime loads a trusted skill only when its
file hash matches this manifest, so a skill edited after the image was built is skipped, not trusted.
Usage: build_manifest.py [DIR]   (default: this script's directory)"""
import hashlib
import json
import re
import sys
from pathlib import Path

d = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
manifest = {}
for p in sorted(d.glob("*.md")):
    raw = p.read_bytes()
    name = re.search(rb"^name:\s*(\S+)\s*$", raw, re.M)
    if not name:
        sys.exit("no name in " + p.name)
    manifest[name.group(1).decode()] = hashlib.sha256(raw).hexdigest()
(d / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
print(len(manifest), "skills pinned")
