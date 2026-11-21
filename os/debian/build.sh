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
  --bootappend-live "boot=live components console=ttyS0,115200n8"
cp -a -- "$repo/os/debian/config/." "$out/config/"
case "${AIWS_OS_PROFILE:-full}" in
  full) ;;
  smoke)
    # Real bootable XFCE+Agent+React ISO with fewer optional compilers.
    cp -- "$repo/os/debian/profiles/smoke.list.chroot" "$out/config/package-lists/aiws-desktop.list.chroot"
    ;;
  *) echo 'AIWS_OS_PROFILE must be full or smoke' >&2; exit 2;;
esac
mkdir -p -- "$out/config/includes.chroot/usr/local/lib/aiws"
cp -a -- "$repo/os/runtime/aiws_toolplane.py" "$repo/os/runtime/aiws_mcp.py" "$repo/os/runtime/aiws_crossplatform.py" "$repo/os/runtime/aiws_codeintel.py" "$repo/os/runtime/aiws_workbench.py" "$repo/os/runtime/aiws_guest_boundary.py" "$repo/os/runtime/aiws_tasks.py" "$repo/os/runtime/aiws_local_model.py" "$repo/os/runtime/aiws_model_router.py" "$repo/os/runtime/aiws_events.py" "$repo/os/runtime/aiws_cli_adapters.py" "$repo/os/runtime/aiws_guest_ops.py" "$repo/os/runtime/aiws_model_registry.py" "$repo/os/runtime/aiws_agent_service.py" "$repo/os/runtime/aiws_agent_client.py" "$repo/os/runtime/aiws_permission_broker.py" "$repo/os/runtime/aiws_boot_slots.py" "$repo/os/runtime/aiws_windows_compat.py" "$out/config/includes.chroot/usr/local/lib/aiws/"
cp -- "$repo/os/verify/aiws_guest_lifecycle_smoke.py" "$out/config/includes.chroot/usr/local/lib/aiws/aiws_guest_lifecycle_smoke.py"
ui="$repo/desktop/AIWorkstation.Frontend/dist"
if [[ ! -s "$ui/index.html" ]]; then
  echo "ERROR: Build the shared React workbench first (cd desktop/AIWorkstation.Frontend && npm install && npm run build)." >&2
  exit 1
fi
mkdir -p -- "$out/config/includes.chroot/usr/local/share/aiws/workbench"
cp -a -- "$ui/." "$out/config/includes.chroot/usr/local/share/aiws/workbench/"

# Optional model-inclusive ISO, prepared only in an isolated licensed builder.
# Never fetch model weights from a running VM or access any host directory.
if [[ -v AIWS_OS_BUNDLED_MODEL_GGUF || -v AIWS_OS_BUNDLED_LLAMA_SERVER ]]; then
  [[ "$AIWS_OS_MODEL_LICENSE_REVIEWED" == "1" ]] || {
    echo "ERROR: user must review source and quantization licenses" >&2; exit 2;
  }
  [[ "$AIWS_OS_MODEL_GGUF_SHA256" =~ ^[a-f0-9]{64}$ ]] || exit 2
  [[ "$AIWS_OS_LLAMA_SERVER_SHA256" =~ ^[a-f0-9]{64}$ ]] || exit 2
  for source in "$AIWS_OS_BUNDLED_MODEL_GGUF" "$AIWS_OS_BUNDLED_LLAMA_SERVER"; do
    [[ -f "$source" && ! -L "$source" ]] || {
      echo "ERROR: only plain local builder files may be packaged" >&2; exit 2;
    }
  done
  [[ "$(sha256sum -- "$AIWS_OS_BUNDLED_MODEL_GGUF" | cut -d' ' -f1)" == "$AIWS_OS_MODEL_GGUF_SHA256" ]] || {
    echo "ERROR: actual GGUF checksum mismatch" >&2; exit 2;
  }
  [[ "$(sha256sum -- "$AIWS_OS_BUNDLED_LLAMA_SERVER" | cut -d' ' -f1)" == "$AIWS_OS_LLAMA_SERVER_SHA256" ]] || {
    echo "ERROR: llama-server checksum mismatch" >&2; exit 2;
  }
  [[ "$(head -c4 -- "$AIWS_OS_BUNDLED_MODEL_GGUF")" == "GGUF" ]] || {
    echo "ERROR: model GGUF magic mismatch" >&2; exit 2;
  }
  preload="$out/config/includes.chroot/usr/local/share/aiws/model-preload"
  install -d -m 0755 "$preload"
  install -m 0444 "$AIWS_OS_BUNDLED_MODEL_GGUF" "$preload/aiws-local.gguf"
  install -m 0755 "$AIWS_OS_BUNDLED_LLAMA_SERVER" \
    "$out/config/includes.chroot/usr/local/bin/llama-server"
  printf '{"modelId":"Qwen/Qwen3.5-2B","sha256":"%s","source":"license-reviewed-builder-source","licenseReviewed":true}\n' \
    "$AIWS_OS_MODEL_GGUF_SHA256" > "$preload/manifest.json"
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
    mkdir -p "$out/config/includes.chroot/etc/aiws"
    printf 'AIWS_MODEL_CI_ONLY=1\n' \
      > "$out/config/includes.chroot/etc/aiws/guest-model-acceptance"
    echo "Strict real-model guest QEMU acceptance enabled for disposable CI only."
  fi
fi

chmod 755 "$out/config/includes.chroot/usr/local/bin/aiws-broker" \
  "$out/config/includes.chroot/usr/local/bin/aiws-agent" \
  "$out/config/includes.chroot/usr/local/bin/aiws-session" \
  "$out/config/includes.chroot/usr/local/bin/aiws-toolctl" \
  "$out/config/includes.chroot/usr/local/bin/aiws-workbench" \
  "$out/config/includes.chroot/usr/local/bin/aiws-open-workbench" \
  "$out/config/includes.chroot/usr/local/bin/aiws-boot-smoke"
echo "Building AIWS OS Live ISO using Debian package repositories..."
lb build
iso="$out/live-image-amd64.hybrid.iso"
if [[ ! -s "$iso" ]]; then echo "ERROR: live-build did not produce expected ISO ($iso)" >&2; exit 1; fi
(cd "$out" && sha256sum -- "${iso##*/}" > "${iso##*/}.sha256")
echo "Image: $iso"
echo "SHA256: $iso.sha256"
echo "NOTICE: ISO boot, guest privilege boundaries, kernel config and host VM isolation remain unverified."
