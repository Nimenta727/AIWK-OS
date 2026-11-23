#!/usr/bin/env bash
# Build AIWS OS from Debian 13 official repositories; never touch host VM disks.
set -Eeuo pipefail
umask 022
repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
out="${AIWS_OS_OUTPUT:-$repo/out/aiws-os}"
if [[ "$(id -u)" -ne 0 ]]; then
  echo "ERROR: Debian live-build requires root/chroot privileges; run this build in a disposable Debian 13 builder." >&2
  exit 1
fi
if [[ ! -r /etc/os-release ]] || ! grep -Eq '^VERSION_CODENAME=trixie$' /etc/os-release; then
  echo "ERROR: build inside Debian 13 (trixie), not your daily-use host." >&2
  exit 1
fi
for cmd in lb debootstrap xorriso mksquashfs sha256sum; do
  command -v "$cmd" >/dev/null || { echo "Missing build dependency: $cmd" >&2; exit 1; }
done
if [[ -e "$out" ]]; then
  echo "ERROR: output already exists ($out). Choose a new AIWS_OS_OUTPUT; nothing was deleted." >&2
  exit 1
fi
mkdir -p -- "$out"
cd -- "$out"
lb config --distribution trixie --architectures amd64 --binary-images iso-hybrid \
  --debian-installer none --archive-areas main --linux-flavours amd64 \
  --bootappend-live "boot=live components console=ttyS0,115200n8 video=1920x1080"
cp -a -- "$repo/os/debian/config/." "$out/config/"
case "${AIWS_OS_PROFILE:-full}" in
  full) ;;
  smoke)
    # Real bootable XFCE+Agent+React ISO with fewer optional compilers.
    cp -- "$repo/os/debian/profiles/smoke.list.chroot" "$out/config/package-lists/aiws-desktop.list.chroot"
    rm -f -- "$out/config/package-lists/aiws-devtools.list.chroot"   # the developer toolchain belongs to the full profile only
    ;;
  *) echo 'AIWS_OS_PROFILE must be full or smoke' >&2; exit 2;;
esac
mkdir -p -- "$out/config/includes.chroot/usr/local/lib/aiws"
# Runtime modules come from os/runtime/MODULES (single source of truth; checked by test_runtime_manifest.py)
while IFS= read -r module; do
  case "$module" in ''|'#'*) continue;; esac
  case "$module" in aiws_*.py) ;; *) echo "Bad entry in os/runtime/MODULES: $module" >&2; exit 2;; esac
  cp -a -- "$repo/os/runtime/$module" "$out/config/includes.chroot/usr/local/lib/aiws/$module"
done < "$repo/os/runtime/MODULES"
cp -- "$repo/os/verify/aiws_guest_lifecycle_smoke.py" "$out/config/includes.chroot/usr/local/lib/aiws/aiws_guest_lifecycle_smoke.py"
ui="$repo/workbench/dist"
if [[ ! -s "$ui/index.html" ]]; then
  echo "ERROR: Build the React workbench first (cd workbench && npm install && npm run build)." >&2
  exit 1
fi
# Trusted skills ship read-only; the manifest pins each file's hash (a changed skill is not loaded).
mkdir -p -- "$out/config/includes.chroot/usr/local/share/aiws/skills"
cp -- "$repo"/os/skills/*.md "$out/config/includes.chroot/usr/local/share/aiws/skills/"
python3 "$repo/os/skills/build_manifest.py" "$out/config/includes.chroot/usr/local/share/aiws/skills" >/dev/null
# System plugins (text only: skills, commands, guards). Same rule as skills: read-only in the image, pinned by tree hash.
mkdir -p -- "$out/config/includes.chroot/usr/local/share/aiws/plugins"
cp -a -- "$repo"/os/plugins/aiws-* "$out/config/includes.chroot/usr/local/share/aiws/plugins/"
python3 "$repo/os/plugins/build_manifest.py" "$out/config/includes.chroot/usr/local/share/aiws/plugins" >/dev/null
mkdir -p -- "$out/config/includes.chroot/usr/local/share/aiws/workbench"
cp -a -- "$ui/." "$out/config/includes.chroot/usr/local/share/aiws/workbench/"

# llama-server (the inference program) can ship WITHOUT any model weights: the release ISO does exactly that, and the customer downloads
# the weights themselves (docs/AIWS_MODEL_WEIGHTS.md). Both pieces are optional and independent.
if [[ -v AIWS_OS_BUNDLED_LLAMA_SERVER ]]; then
  [[ "${AIWS_OS_LLAMA_SERVER_SHA256:-}" =~ ^[a-f0-9]{64}$ ]] || { echo "ERROR: AIWS_OS_LLAMA_SERVER_SHA256 is required" >&2; exit 2; }
  [[ -f "$AIWS_OS_BUNDLED_LLAMA_SERVER" && ! -L "$AIWS_OS_BUNDLED_LLAMA_SERVER" ]] || {
    echo "ERROR: only plain local builder files may be packaged" >&2; exit 2;
  }
  [[ "$(sha256sum -- "$AIWS_OS_BUNDLED_LLAMA_SERVER" | cut -d' ' -f1)" == "$AIWS_OS_LLAMA_SERVER_SHA256" ]] || {
    echo "ERROR: llama-server checksum mismatch" >&2; exit 2;
  }
  install -m 0755 "$AIWS_OS_BUNDLED_LLAMA_SERVER" "$out/config/includes.chroot/usr/local/bin/llama-server"
  echo "llama-server included in the guest ISO (no model weights unless AIWS_OS_BUNDLED_MODEL_GGUF is also set)."
fi

# Optional model-inclusive ISO, prepared only in an isolated licensed builder (used by the CI pipeline smoke; the release does not use it).
# Never fetch model weights from a running VM or access any host directory.
if [[ -v AIWS_OS_BUNDLED_MODEL_GGUF ]]; then
  [[ "${AIWS_OS_MODEL_LICENSE_REVIEWED:-}" == "1" ]] || {
    echo "ERROR: user must review source and quantization licenses" >&2; exit 2;
  }
  [[ "${AIWS_OS_MODEL_GGUF_SHA256:-}" =~ ^[a-f0-9]{64}$ ]] || exit 2
  [[ -f "$AIWS_OS_BUNDLED_MODEL_GGUF" && ! -L "$AIWS_OS_BUNDLED_MODEL_GGUF" ]] || {
    echo "ERROR: only plain local builder files may be packaged" >&2; exit 2;
  }
  [[ "$(sha256sum -- "$AIWS_OS_BUNDLED_MODEL_GGUF" | cut -d' ' -f1)" == "$AIWS_OS_MODEL_GGUF_SHA256" ]] || {
    echo "ERROR: actual GGUF checksum mismatch" >&2; exit 2;
  }
  [[ "$(head -c4 -- "$AIWS_OS_BUNDLED_MODEL_GGUF")" == "GGUF" ]] || {
    echo "ERROR: model GGUF magic mismatch" >&2; exit 2;
  }
  preload="$out/config/includes.chroot/usr/local/share/aiws/model-preload"
  install -d -m 0755 "$preload"
  install -m 0444 "$AIWS_OS_BUNDLED_MODEL_GGUF" "$preload/aiws-local.gguf"
  model_id="${AIWS_OS_MODEL_ID:-Qwen/Qwen3.5-9B}"
  [[ "$model_id" =~ ^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$ ]] || { echo "ERROR: invalid AIWS_OS_MODEL_ID" >&2; exit 2; }
  printf '{"modelId":"%s","sha256":"%s","source":"license-reviewed-builder-source","licenseReviewed":true}\n' \
    "$model_id" "$AIWS_OS_MODEL_GGUF_SHA256" > "$preload/manifest.json"
  chmod 0444 "$preload/manifest.json"
  echo "Offline model included in guest ISO with SHA256 provenance; activation remains opt-in."
  if [[ "${AIWS_OS_MODEL_GUEST_CI_TEST:-0}" == "1" ]]; then
    install -m 0444 "$repo/os/model/ci/guest_inference_smoke.py" \
      "$out/config/includes.chroot/usr/local/lib/aiws/aiws_model_guest_smoke.py"
    install -m 0444 "$repo/os/model/ci/guest_benchmark.py" \
      "$out/config/includes.chroot/usr/local/lib/aiws/guest_benchmark.py"
    install -m 0444 "$repo/os/model/ci/heldout_v1.jsonl" \
      "$out/config/includes.chroot/usr/local/lib/aiws/aiws_model_heldout.jsonl"
    install -m 0444 "$repo/os/model/ci/heldout_v2.jsonl" \
      "$out/config/includes.chroot/usr/local/lib/aiws/aiws_model_heldout_v2.jsonl"
    install -m 0444 "$repo/os/model/ci/heldout_v3.jsonl" \
      "$out/config/includes.chroot/usr/local/lib/aiws/aiws_model_heldout_v3.jsonl"
    mkdir -p "$out/config/includes.chroot/etc/aiws"
    printf 'AIWS_MODEL_CI_ONLY=1\n' \
      > "$out/config/includes.chroot/etc/aiws/guest-model-acceptance"
    echo "Strict real-model guest QEMU acceptance enabled for disposable CI only."
  fi
fi

# Builder lane (step O4): root-run self-test, correct modes for sudoers/firewall files.
install -d -m 0755 "$out/config/includes.chroot/usr/local/sbin"
install -m 0755 "$repo/os/builder/aiws_builder_selftest.py" "$out/config/includes.chroot/usr/local/sbin/aiws-builder-selftest"
chmod 0440 "$out/config/includes.chroot/etc/sudoers.d/aiws-builder"
chmod 0644 "$out/config/includes.chroot/etc/aiws/builder-firewall.nft" "$out/config/includes.chroot/etc/aiws/egress-allow.conf"
# AIWS Code (Code - OSS based IDE): launcher, icons and, only if a verified tarball is supplied, the program itself.
install -d -m 0755 "$out/config/includes.chroot/usr/share/icons/hicolor/256x256/apps" "$out/config/includes.chroot/usr/share/icons/hicolor/scalable/apps"
install -m 0644 "$repo/os/ide/branding/icon-256.png" "$out/config/includes.chroot/usr/share/icons/hicolor/256x256/apps/aiws-code.png"
install -m 0644 "$repo/os/ide/branding/aiws-code.svg" "$out/config/includes.chroot/usr/share/icons/hicolor/scalable/apps/aiws-code.svg"
chmod 755 "$out/config/includes.chroot/usr/local/bin/aiws-code"
if [[ -v AIWS_CODE_TARBALL ]]; then
  [[ "${AIWS_CODE_SHA256:-}" =~ ^[a-f0-9]{64}$ ]] || { echo "ERROR: AIWS_CODE_SHA256 must be the tarball's SHA-256" >&2; exit 2; }
  [[ -f "$AIWS_CODE_TARBALL" && ! -L "$AIWS_CODE_TARBALL" ]] || { echo "ERROR: AIWS_CODE_TARBALL must be a plain local file" >&2; exit 2; }
  [[ "$(sha256sum -- "$AIWS_CODE_TARBALL" | cut -d' ' -f1)" == "$AIWS_CODE_SHA256" ]] || { echo "ERROR: AIWS Code checksum mismatch" >&2; exit 2; }
  command -v zstd >/dev/null || { echo "Missing build dependency: zstd" >&2; exit 1; }
  mkdir -p -- "$out/config/includes.chroot/opt/aiws-code"
  zstd -dc -- "$AIWS_CODE_TARBALL" | tar -x --strip-components=1 -C "$out/config/includes.chroot/opt/aiws-code"
  for legal in LICENSE.txt ThirdPartyNotices.txt AIWS-NOTICE.md; do
    [[ -s "$out/config/includes.chroot/opt/aiws-code/$legal" ]] || { echo "ERROR: $legal is missing from the AIWS Code package: refusing to ship without the license files" >&2; exit 2; }
  done
  echo "AIWS Code included in the image (verified SHA-256)."
else
  echo "NOTE: no AIWS_CODE_TARBALL given: the image contains the launcher but not the editor itself."
fi

chmod 755 "$out/config/includes.chroot/usr/local/bin/aiws-broker" \
  "$out/config/includes.chroot/usr/local/bin/aiws-agent" \
  "$out/config/includes.chroot/usr/local/bin/aiws-session" \
  "$out/config/includes.chroot/usr/local/bin/aiws-toolctl" \
  "$out/config/includes.chroot/usr/local/bin/aiws-workbench" \
  "$out/config/includes.chroot/usr/local/bin/aiws-open-workbench" \
  "$out/config/includes.chroot/usr/local/bin/aiws-boot-smoke"
echo "Building AIWS OS Live ISO using Debian package repositories..."
# Optional Swift toolchain (about 2 GB installed): AIWS_WITH_SWIFT=1. The packages come from Debian 13 main like everything else.
if [[ "${AIWS_WITH_SWIFT:-0}" == "1" ]]; then
  cp -- "$repo/os/debian/optional/aiws-swift.list.chroot" "$out/config/package-lists/aiws-swift.list.chroot"
  echo "Swift toolchain (swiftlang) will be included: the image will be about 2 GB larger when installed."
fi
# System file manifest (the LAST staging step, so it covers everything above): the guest re-checks it at every boot
# (aiws-verify-system.service) because the live system's writable overlay would otherwise hide a modified file.
mkdir -p -- "$out/config/includes.chroot/usr/local/share/aiws/docs"
cp -- "$repo/docs/AIWS_DUAL_DISK.md" "$out/config/includes.chroot/usr/local/share/aiws/docs/AIWS_DUAL_DISK.md"
python3 "$repo/os/runtime/aiws_sysverify.py" build "$out/config/includes.chroot/usr/local/share/aiws/system.sha256.json" "$out/config/includes.chroot"
lb build
iso="$out/live-image-amd64.hybrid.iso"
if [[ ! -s "$iso" ]]; then echo "ERROR: live-build did not produce expected ISO ($iso)" >&2; exit 1; fi
(cd "$out" && sha256sum -- "${iso##*/}" > "${iso##*/}.sha256")
echo "Image: $iso"
echo "SHA256: $iso.sha256"
echo "NOTICE: ISO boot, guest privilege boundaries, kernel config and host VM isolation remain unverified."
