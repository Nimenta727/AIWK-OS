#!/usr/bin/env bash
# True El Torito ISO firmware boot, not the separate -kernel diagnostics.
set -Eeuo pipefail
[[ $# -eq 3 ]] || { echo 'usage: firmware-iso-boot.sh ISO OUT bios|uefi' >&2; exit 2; }
iso="$(realpath "$1")"
out="$(realpath -m "$2")"
firmware="$3"
[[ "$firmware" == bios || "$firmware" == uefi ]] || exit 2
[[ -s "$iso" ]] || exit 1
for cmd in qemu-system-x86_64 xorriso; do command -v "$cmd" >/dev/null || exit 1; done
mkdir -p "$out"
xorriso -indev "$iso" -report_el_torito plain > "$out/el-torito.txt"
xorriso -indev "$iso" -report_system_area plain > "$out/system-area.txt"
grep -Eq 'El Torito boot img.*BIOS' "$out/el-torito.txt" || {
 echo 'AIWS_FIRMWARE_ISO_FAIL missing BIOS record' >&2; exit 1;
}
grep -Eq 'El Torito boot img.*(UEFI|EFI)' "$out/el-torito.txt" || {
 echo 'AIWS_FIRMWARE_ISO_FAIL missing UEFI record' >&2; exit 1;
}
launch() {
 qemu-system-x86_64 -machine q35,accel=tcg -cpu max -smp 2 -m 4096 \
   -boot order=d,menu=off -cdrom "$iso" \
   -nic none -display none -vga std -monitor none \
   -serial "file:$out/boot-serial.log" -no-reboot \
   -sandbox on,obsolete=deny,elevateprivileges=deny,spawn=deny,resourcecontrol=deny "$@"
}
if [[ "$firmware" == uefi ]]; then
  code=""
  vars=""
  for dir in /usr/share/OVMF /usr/share/ovmf /usr/share/qemu; do
    for suffix in _4M ""; do
      if [[ -s "$dir/OVMF_CODE$suffix.fd" && -s "$dir/OVMF_VARS$suffix.fd" ]]; then
        code="$dir/OVMF_CODE$suffix.fd"
        vars="$dir/OVMF_VARS$suffix.fd"
        break
      fi
    done
    [[ -n "$code" ]] && break
  done
  [[ -n "$code" ]] || { echo 'AIWS_FIRMWARE_ISO_FAIL missing OVMF pair' >&2; exit 1; }
  cp -- "$vars" "$out/ovmf-vars.fd"
  launch -drive "if=pflash,format=raw,readonly=on,file=$code" \
    -drive "if=pflash,format=raw,file=$out/ovmf-vars.fd" &
else
  launch &
fi
pid=$!
trap 'kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true' EXIT
echo "AIWS_FIRMWARE_ISO_START firmware=$firmware"
passed=0
for _ in $(seq 1 650); do
  if [[ -f "$out/boot-serial.log" ]] &&
     grep -q 'AIWS_BOOT_SMOKE_PASS' "$out/boot-serial.log"; then
    passed=1
    break
  fi
  if [[ -f "$out/boot-serial.log" ]] &&
     grep -q 'AIWS_BOOT_SMOKE_FAIL' "$out/boot-serial.log"; then break; fi
  if ! kill -0 "$pid" 2>/dev/null; then break; fi
  sleep 2
done
tail -n 160 "$out/boot-serial.log" 2>/dev/null || true
[[ "$passed" == 1 ]] || { echo "AIWS_FIRMWARE_ISO_FAIL firmware=$firmware" >&2; exit 1; }
echo "AIWS_FIRMWARE_ISO_PASS firmware=$firmware el_torito=yes gui_dag=yes"
