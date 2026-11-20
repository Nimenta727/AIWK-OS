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
cp -a -- "$repo/os/runtime/aiws_toolplane.py" "$repo/os/runtime/aiws_mcp.py" "$repo/os/runtime/aiws_crossplatform.py" "$repo/os/runtime/aiws_codeintel.py" "$repo/os/runtime/aiws_workbench.py" "$repo/os/runtime/aiws_guest_boundary.py" "$repo/os/runtime/aiws_tasks.py" "$repo/os/runtime/aiws_local_model.py" "$repo/os/runtime/aiws_guest_ops.py" "$out/config/includes.chroot/usr/local/lib/aiws/"
ui="$repo/desktop/AIWorkstation.Frontend/dist"
if [[ ! -s "$ui/index.html" ]]; then
  echo "ERROR: Build the shared React workbench first (cd desktop/AIWorkstation.Frontend && npm install && npm run build)." >&2
  exit 1
fi
mkdir -p -- "$out/config/includes.chroot/usr/local/share/aiws/workbench"
cp -a -- "$ui/." "$out/config/includes.chroot/usr/local/share/aiws/workbench/"
chmod 755 "$out/config/includes.chroot/usr/local/bin/aiws-session" \
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
