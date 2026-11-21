# AIWS Code: the IDE of AIWS OS

AIWS OS is built for programmers, so it ships a full code editor. **AIWS Code is a rebranded build of the open-source
Code - OSS web server** (the MIT-licensed core that Microsoft's "Visual Studio Code" is built from), compiled from
source at a pinned commit, running **on loopback only** inside the guest and shown in a Chromium app window.
Read [NOTICE.md](NOTICE.md) for the licensing: the MIT credits stay, Microsoft's name, logos, marketplace and services do not.

## Status (read this first)
| Item | State |
| --- | --- |
| Upstream facts (tag, commit, Node/pnpm versions, gulp task, server flags, `product.json` keys, CSP) | **Read from the real 1.147.0 source** |
| `product.overrides.json` | **Verified**: applied to the real upstream `product.json` it leaves **0 service endpoints and 0 brand strings** (provenance fields excepted) |
| `patches/0001-local-webview-endpoint.patch` | **Verified** to apply cleanly to the real pinned source (`git apply --check`) |
| Launcher `aiws-code` | **Tested** as an unprivileged user against a fake server (flags, token, seeding, refusal cases) |
| `build-aiws-code.sh` | Written from the real sources; **NOT built**: never executed end to end by its author. The first run is the acceptance test |
| The patched webview endpoint working in a browser | **unverified** (needs a build) |
| Extension compatibility, performance, memory | **unverified** |

## What is in this folder
| Path | Purpose |
| --- | --- |
| `PIN.env` | upstream repository, tag `1.147.0`, commit, Node `24.22.1` and pnpm `12.16.0` exactly as upstream pins them |
| `product.overrides.json` | our identity (`AIWS Code`, `aiws-code`, data folders, URL protocol), Open VSX instead of Microsoft's marketplace, no Copilot/voice/auth defaults, local webview endpoint |
| `patches/` | source patches (checked with `git apply --check` before applying) |
| `branding/` | our own original artwork (SVG source + PNG/ICO) |
| `tools/` | `apply_product_overrides.py` (fails if any Microsoft endpoint or brand string would remain), `scan_endpoints.py` (also audits a built tree) |
| `build-aiws-code.sh` | clone, verify commit, rebrand, patch, build `vscode-reh-web-linux-x64`, add legal files, audit, package |
| `NOTICE.md` | provenance and what we do and do not reuse |

The launcher and `.desktop` entry live in the image tree (`os/debian/config/includes.chroot/usr/local/bin/aiws-code`).

## Build (on a networked builder, never inside the offline guest)
```bash
# Node 24.22.1 and pnpm 12.16.0 must be installed; ~10+ GB free disk, several GB RAM.
os/ide/build-aiws-code.sh                      # produces aiws-code-1.147.0-linux-x64.tar.zst (+ .sha256)
AIWS_CODE_TARBALL=... AIWS_CODE_SHA256=... sudo ./os/debian/build.sh   # include it in the ISO (checksum verified)
```
Without `AIWS_CODE_TARBALL` the image contains only the launcher and prints "not installed".

## How it runs
`aiws-code` starts `/opt/aiws-code/bin/aiws-code-server --host 127.0.0.1 --port 18090 --connection-token-file ... --telemetry-level off
--enable-remote-auto-shutdown` (shuts down after the last window closes) and opens `http://127.0.0.1:18090/?tkn=...` in a
Chromium app window. Settings are seeded once (telemetry off, no update checks, AI features off). Port 18090 is fixed because the
webview endpoint (`http://{{uuid}}.localhost:18090/static/out/...`) points at it.

## Why a patch is needed
Upstream's web build loads webview content (Markdown preview, extension panels) from `https://*.vscode-cdn.net`, a Microsoft
CDN, and hardcodes that host in its Content-Security-Policy. An offline guest cannot reach it and we do not want to depend on it,
so the patch points both at the local `/static/out/...` route of the same server.

## Known limits (honest list)
* About 48 upstream source files still mention "Visual Studio Code" in help text and links; the product name shown in the UI
  comes from `product.json`, but some documentation strings and links remain. `endpoint-report.json` (generated at build time)
  lists the service hosts that remain in the built output so they can be reviewed.
* The upstream tree still contains the GitHub Copilot extension code. Its defaults are removed and AI features are disabled
  in the seeded settings, but the code is not stripped from the package.
* Microsoft's proprietary extensions (Pylance, C# Dev Kit, Remote-SSH, ...) are not available; use open alternatives from Open VSX.
  The guest is offline by default, so install extensions from `.vsix` files or enable the builder network lane.
* The IDE's integrated terminal runs as the guest user (it is YOUR tool, unlike the model, which has no network).
