#!/usr/bin/env bash
# Build "AIWS Code" (a rebranded, MIT-licensed build of the Code - OSS web server) at a pinned upstream commit.
# Run on a NETWORKED builder (pnpm registry, GitHub for built-in extensions, nodejs.org for the bundled node).
# NEVER run this inside the offline AIWS guest. Output goes to $AIWS_CODE_WORK (must not exist yet).
#
# STATUS: written from the real upstream sources at the pinned tag, but NOT yet executed end to end by its author
# (the build needs ~10+ GB disk, several GB RAM and a long time). Treat the first run as the acceptance test.
set -Eeuo pipefail
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=PIN.env
source "$here/PIN.env"
if [[ "$(id -u)" -eq 0 ]]; then echo "ERROR: do not build as root." >&2; exit 1; fi
for cmd in git node pnpm python3 tar zstd sha256sum; do
  command -v "$cmd" >/dev/null || { echo "Missing build tool: $cmd" >&2; exit 1; }
done
if [[ "$(node -v)" != "v$AIWS_CODE_NODE_VERSION" ]]; then
  echo "ERROR: upstream requires Node $AIWS_CODE_NODE_VERSION exactly (found $(node -v))." >&2; exit 1
fi
if [[ "$(pnpm -v)" != "$AIWS_CODE_PNPM_VERSION" ]]; then
  echo "ERROR: upstream pins pnpm $AIWS_CODE_PNPM_VERSION (found $(pnpm -v))." >&2; exit 1
fi
work="${AIWS_CODE_WORK:-$PWD/aiws-code-build}"
if [[ -e "$work" ]]; then echo "ERROR: $work already exists; choose a new AIWS_CODE_WORK (nothing was deleted)." >&2; exit 1; fi
mkdir -p -- "$work"
cd -- "$work"
git clone --depth 1 --branch "$AIWS_CODE_VSCODE_TAG" "$AIWS_CODE_VSCODE_REPO" src
if [[ "$(git -C src rev-parse HEAD)" != "$AIWS_CODE_VSCODE_COMMIT" ]]; then
  echo "ERROR: tag $AIWS_CODE_VSCODE_TAG does not point at the pinned commit (possible tampering)." >&2; exit 1
fi

# 1) Our own product identity; fails if any Microsoft service endpoint or brand string would remain.
python3 "$here/tools/apply_product_overrides.py" src/product.json "$here/product.overrides.json" src/product.json.new
mv -- src/product.json.new src/product.json
# 2) Source patches (checked first so a drifted upstream fails loudly).
for patch in "$here"/patches/*.patch; do
  git -C src apply --check "$patch"
  git -C src apply "$patch"
done
# 3) Our artwork replaces the upstream icons (we never ship upstream logos).
install -m 0644 "$here/branding/icon-192.png" src/resources/server/code-192.png
install -m 0644 "$here/branding/icon-512.png" src/resources/server/code-512.png
install -m 0644 "$here/branding/favicon.ico"  src/resources/server/favicon.ico
install -m 0644 "$here/branding/icon-256.png" src/resources/linux/code.png
python3 - <<'PY'
import json
p = "src/resources/server/manifest.json"
m = json.load(open(p))
m["name"], m["short_name"] = "AIWS Code", "AIWS Code"
open(p, "w").write(json.dumps(m, indent="\t") + "\n")
PY
# 4) (Account-service extensions are removed from the OUTPUT after the build, below: the upstream gulp graph reads their
#    tsconfig.json, so deleting the source directories first breaks the build - found in the first real run.)

( cd src && pnpm install --frozen-lockfile && pnpm run gulp vscode-reh-web-linux-x64-min-ci )

out="$work/vscode-reh-web-linux-x64"      # upstream writes next to the source tree (BUILD_ROOT = dirname(REPO_ROOT))
[[ -x "$out/node" || -f "$out/out/server-main.js" ]] || { echo "ERROR: expected server output not found in $out" >&2; exit 1; }
# 4b) Built-in extensions that only talk to Microsoft/GitHub account services are not needed offline: drop them from the output.
rm -rf -- "$out/extensions/microsoft-authentication" "$out/extensions/github-authentication"
# 5) Legal: the MIT license and third-party notices MUST travel with every copy (they are not "branding").
install -m 0644 src/LICENSE.txt "$out/LICENSE.txt"
install -m 0644 src/ThirdPartyNotices.txt "$out/ThirdPartyNotices.txt"
install -m 0644 "$here/NOTICE.md" "$out/AIWS-NOTICE.md"
# 6) Audit: which service hosts are still present in the built output (report-only, kept with the package).
python3 "$here/tools/scan_endpoints.py" tree "$out" > "$out/endpoint-report.json"
cp -- src/product.json "$out/product.json.used"
patches_json="$(for p in "$here"/patches/*.patch; do printf '{"file":"%s","sha256":"%s"},' "$(basename "$p")" "$(sha256sum "$p" | cut -d' ' -f1)"; done)"
cat > "$out/PROVENANCE.json" <<JSON
{
  "product": "AIWS Code",
  "upstream": "Code - OSS (MIT licensed)",
  "upstreamTag": "$AIWS_CODE_VSCODE_TAG",
  "upstreamCommit": "$AIWS_CODE_VSCODE_COMMIT",
  "node": "$AIWS_CODE_NODE_VERSION",
  "pnpm": "$AIWS_CODE_PNPM_VERSION",
  "productOverridesSha256": "$(sha256sum "$here/product.overrides.json" | cut -d' ' -f1)",
  "patches": [${patches_json%,}],
  "builtAt": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
JSON
tar -C "$work" -cf - vscode-reh-web-linux-x64 | zstd -19 -T0 -o "$work/aiws-code-$AIWS_CODE_VSCODE_TAG-linux-x64.tar.zst"
( cd "$work" && sha256sum "aiws-code-$AIWS_CODE_VSCODE_TAG-linux-x64.tar.zst" > "aiws-code-$AIWS_CODE_VSCODE_TAG-linux-x64.tar.zst.sha256" )
echo "Built: $work/aiws-code-$AIWS_CODE_VSCODE_TAG-linux-x64.tar.zst"
echo "Review $out/endpoint-report.json before shipping. Include the tarball in the ISO with AIWS_CODE_TARBALL/AIWS_CODE_SHA256."
