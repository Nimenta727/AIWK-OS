#!/usr/bin/env python3
"""Write manifest.json (plugin name -> tree sha256) for the plugins in a directory. The runtime enables a SYSTEM plugin only when its
tree hash matches this manifest, so a plugin edited after the image was built is not trusted.
Usage: build_manifest.py [DIR]   (default: this script's directory). Run it from the same checkout the runtime modules come from."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))
import aiws_plugins as P

d = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
manifest = {}
for entry in sorted(d.iterdir()):
    if not entry.is_dir() or entry.name.startswith("."):
        continue
    rec = P.load_plugin(entry, "system")
    if not rec["valid"]:
        sys.exit("plugin %s is not valid: %s" % (entry.name, "; ".join(rec["problems"][:3])))
    manifest[rec["name"]] = rec["treeSha256"]
(d / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
print(len(manifest), "plugins pinned")
