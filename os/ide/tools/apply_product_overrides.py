#!/usr/bin/env python3
"""Merge product.overrides.json into the upstream product.json (top-level keys; null deletes a key).

Usage: apply_product_overrides.py UPSTREAM_PRODUCT.json OVERRIDES.json OUT.json
Fails (exit 1) if the merged result still contains a service endpoint or Microsoft/VS Code/Copilot brand string.
"""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scan_endpoints import scan_product

REQUIRED = ("nameShort", "nameLong", "applicationName", "dataFolderName", "serverApplicationName", "urlProtocol")

def merge(upstream, overrides):
    out = dict(upstream)
    for key, value in overrides.items():
        if value is None:
            out.pop(key, None)
        else:
            out[key] = value
    return out

def main(argv):
    if len(argv) != 4:
        print(__doc__); return 2
    upstream = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    merged = merge(upstream, json.loads(Path(argv[2]).read_text(encoding="utf-8")))
    missing = [k for k in REQUIRED if not isinstance(merged.get(k), str) or not merged[k]]
    bad = [f for f in scan_product(merged) if f["class"] in ("service", "brand")]
    if missing or bad:
        print(json.dumps({"missingRequired": missing, "findings": bad}, indent=2)); return 1
    Path(argv[3]).write_text(json.dumps(merged, indent="\t") + "\n", encoding="utf-8")
    print("product.json written: %d keys" % len(merged)); return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
