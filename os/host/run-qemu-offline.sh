#!/usr/bin/env bash
# Experimental OFFLINE Linux KVM launcher. Host/guest boundary lives in QEMU and host policy.
set -Eeuo pipefail
if [[ "${EUID}" -eq 0 ]]; then echo "Refusing to run QEMU as host root." >&2; exit 1; fi
if [[ "$#" -ne 1 ]]; then echo "Usage: $0 /absolute/path/to/live-image-amd64.hybrid.iso" >&2; exit 2; fi
iso="$1"
if [[ ! -f "$iso" || ! -r "$iso" ]]; then echo "ISO missing/unreadable: $iso" >&2; exit 1; fi
case "$iso" in /*) ;; *) echo 'Please supply an absolute ISO path.' >&2; exit 1;; esac
if [[ ! -r /dev/kvm || ! -w /dev/kvm ]]; then
  echo "KVM device unavailable to this user. Refusing software emulation fallback." >&2; exit 1
fi
command -v qemu-system-x86_64 >/dev/null || { echo 'qemu-system-x86_64 is required.' >&2; exit 1; }
echo 'OFFLINE VM: no NIC, host folder mounts, passthrough devices, or guest-agent channel.'
echo 'This launcher has NOT been audited as an isolation boundary; use a disposable, restricted host.'
# Optional second disk for the AI work area (separate from the read-only system): AIWS_WORK_DISK=/abs/path/work.qcow2
# Create it once with: qemu-img create -f qcow2 work.qcow2 40G   (the guest formats it on first boot, only if it is blank)
extra=()
if [[ -n "${AIWS_WORK_DISK:-}" ]]; then
  case "$AIWS_WORK_DISK" in /*) ;; *) echo 'AIWS_WORK_DISK must be an absolute path.' >&2; exit 1;; esac
  [[ -f "$AIWS_WORK_DISK" && -r "$AIWS_WORK_DISK" && -w "$AIWS_WORK_DISK" ]] || { echo "Work disk missing or not writable: $AIWS_WORK_DISK" >&2; exit 1; }
  extra=(-drive "file=$AIWS_WORK_DISK,if=virtio,format=qcow2,cache=none,discard=unmap")
fi
# Memory for the virtual machine in MiB (default 6144). The 9B model needs about 11 GiB when it runs on the guest CPU: use 16384 for it.
mem="${AIWS_VM_MEM:-6144}"
case "$mem" in ''|*[!0-9]*) echo 'AIWS_VM_MEM must be a number of MiB.' >&2; exit 1;; esac
if [ "$mem" -lt 2048 ] || [ "$mem" -gt 65536 ]; then echo 'AIWS_VM_MEM must be between 2048 and 65536.' >&2; exit 1; fi
# Optional READ-ONLY third disk, e.g. one that carries the model weights you downloaded yourself (docs/AIWS_MODEL_WEIGHTS.md). The guest has no
# network by design, so this is how a file gets in. It is attached read-only and is not mounted automatically.
if [[ -n "${AIWS_EXTRA_DISK:-}" ]]; then
  case "$AIWS_EXTRA_DISK" in /*) ;; *) echo 'AIWS_EXTRA_DISK must be an absolute path.' >&2; exit 1;; esac
  [[ -f "$AIWS_EXTRA_DISK" && -r "$AIWS_EXTRA_DISK" ]] || { echo "Extra disk missing or unreadable: $AIWS_EXTRA_DISK" >&2; exit 1; }
  extra+=(-drive "file=$AIWS_EXTRA_DISK,if=virtio,format=raw,readonly=on")
fi
exec qemu-system-x86_64 \
  -machine q35,accel=kvm -cpu host -smp 4 -m "$mem" \
  -boot d -drive "file=$iso,if=ide,media=cdrom,readonly=on,format=raw" "${extra[@]}" \
  -nic none -monitor none -serial none -parallel none \
  -display gtk -vga virtio \
  -sandbox on,obsolete=deny,elevateprivileges=deny,spawn=deny,resourcecontrol=deny
