#!/usr/bin/env python3
"""Scan a product.json or a file tree for Microsoft/GitHub-Copilot service endpoints and brand strings.

Three finding classes:
  service  : a host the product would CALL (CDN, telemetry, update, marketplace, auth, AI). Blocking for product.json.
  doc-link : a documentation link (code.visualstudio.com, aka.ms ...): shown, never blocking.
  brand    : "Visual Studio Code", "VS Code", "Code - OSS", "Copilot", "Microsoft" in a value: blocking for product.json.
Provenance fields (license links, built-in extension repos/metadata) are allowed in product.json: crediting the
original authors is required by the MIT license, it is not a use of their brand.
"""
import json
from pathlib import Path
import re
import sys

SERVICE = re.compile(r"(?i)(?:[a-z0-9\-*{}.]+\.)?(vscode-cdn\.net|vscode-unpkg\.net|msecnd\.net|vsassets\.io|"
                     r"update\.code\.visualstudio\.com|marketplace\.visualstudio\.com|gallery\.vsassets\.io|"
                     r"events\.data\.microsoft\.com|vortex\.data\.microsoft\.com|dc\.services\.visualstudio\.com|"
                     r"experimentation\.visualstudio\.com|prss\.microsoft\.com|graph\.microsoft\.com|login\.microsoftonline\.com|"
                     r"mai\.microsoft\.com|cloudapp\.azure\.com|azureedge\.net|api\.githubcopilot\.com|githubcopilot\.com|"
                     r"copilot-proxy\.githubusercontent\.com|github\.com/login/oauth|api\.github\.com/copilot)")
DOC = re.compile(r"(?i)(?:code\.visualstudio\.com|go\.microsoft\.com|aka\.ms|learn\.microsoft\.com|docs\.microsoft\.com|"
                 r"msdn\.microsoft\.com|developer\.microsoft\.com|www\.microsoft\.com)")
BRAND = re.compile(r"(?i)visual studio code|vs ?code\b|code - oss|copilot|microsoft")
ALLOWED_PATHS = re.compile(r"^(licenseUrl|serverLicenseUrl|builtInExtensions(\[\d+\].*)?)$")
# Not brand use: an internal keymap id, and the wire-protocol name inside Open VSX's API paths (service hosts are still checked).
ALLOWED_BRAND_PATHS = re.compile(r"^(onboardingKeymaps\[\d+\]\.id|extensionsGallery(\..*)?)$")

def walk(value, path=""):
    if isinstance(value, dict):
        for k, v in value.items():
            yield from walk(v, (path + "." + k) if path else k)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from walk(v, "%s[%d]" % (path, i))
    elif isinstance(value, str):
        yield path, value

def scan_product(product):
    findings = []
    for path, value in walk(product):
        if ALLOWED_PATHS.match(path):
            continue
        for m in SERVICE.finditer(value):
            findings.append({"class": "service", "path": path, "match": m.group(0)[:80]})
        if not ALLOWED_BRAND_PATHS.match(path):
            for m in BRAND.finditer(value):
                findings.append({"class": "brand", "path": path, "match": m.group(0)[:40]})
        if DOC.search(value) and not SERVICE.search(value):
            findings.append({"class": "doc-link", "path": path, "match": DOC.search(value).group(0)})
    return findings

def scan_tree(root, skip=("node_modules", ".git"), suffixes=(".js", ".json", ".html", ".css", ".ts", ".mjs"), limit_bytes=8_000_000):
    """Report-only inventory of hosts in a built tree (LICENSE/ThirdPartyNotices are skipped: they must keep the credits)."""
    counts = {}
    for path in Path(root).rglob("*"):
        if (not path.is_file() or path.suffix not in suffixes or any(s in path.parts for s in skip)
                or path.name in ("LICENSE.txt", "ThirdPartyNotices.txt") or path.stat().st_size > limit_bytes):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in SERVICE.finditer(text):
            key = ("service", m.group(1).lower())
            counts.setdefault(key, set()).add(str(path.relative_to(root)))
    return {"%s:%s" % k: sorted(v)[:5] + (["+%d more" % (len(v) - 5)] if len(v) > 5 else []) for k, v in sorted(counts.items())}

def main(argv):
    if len(argv) < 3 or argv[1] not in ("product", "tree"):
        print("usage: scan_endpoints.py product PRODUCT.json | tree DIR"); return 2
    if argv[1] == "product":
        findings = scan_product(json.loads(Path(argv[2]).read_text(encoding="utf-8")))
        print(json.dumps(findings, indent=2))
        return 1 if any(f["class"] in ("service", "brand") for f in findings) else 0
    print(json.dumps(scan_tree(argv[2]), indent=2))
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
