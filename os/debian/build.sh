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
  --bootappend-live "boot=live components quiet"
cp -a -- "$repo/os/debian/config/." "$out/config/"
mkdir -p -- "$out/config/includes.chroot/usr/local/lib/aiws"
cp -a -- "$repo/os/runtime/aiws_toolplane.py" "$repo/os/runtime/aiws_mcp.py" "$repo/os/runtime/aiws_crossplatform.py" "$repo/os/runtime/aiws_codeintel.py" "$out/config/includes.chroot/usr/local/lib/aiws/"
chmod 755 "$out/config/includes.chroot/usr/local/bin/aiws-toolctl"
echo "Building AIWS OS Live ISO using Debian package repositories..."
lb build
iso="$out/live-image-amd64.hybrid.iso"
if [[ ! -s "$iso" ]]; then echo "ERROR: live-build did not produce expected ISO ($iso)" >&2; exit 1; fi
(cd "$out" && sha256sum -- "${iso##*/}" > "${iso##*/}.sha256")
echo "Image: $iso"
echo "SHA256: $iso.sha256"
echo "NOTICE: ISO boot, guest privilege boundaries, kernel config and host VM isolation remain unverified."
