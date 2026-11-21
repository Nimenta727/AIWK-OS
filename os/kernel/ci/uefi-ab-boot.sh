#!/usr/bin/env bash
# CI-only, disposable QEMU disk: real OVMF -> systemd-boot -> broken B -> A.
# Never passes a host filesystem/command API, network or device to the guest.
set -Eeuo pipefail
[[ $# -eq 2 ]] || { echo 'usage: uefi-ab-boot.sh LIVE_ISO OUTPUT_DIR' >&2; exit 2; }
iso="$(realpath "$1")"
out="$(realpath -m "$2")"
mkdir -p "$out"
for cmd in sgdisk mkfs.fat mcopy mmd qemu-system-x86_64 xorriso; do
  command -v "$cmd" >/dev/null || { echo "Missing CI boot dependency: $cmd" >&2; exit 1; }
done
test -s "$iso"
# Avoid find | head with pipefail when a distro-specific search directory is
# absent. Ubuntu 26.10 also ships signed .efi variants on some runners.
bootefi=""
for file in \
  /usr/lib/systemd/boot/efi/systemd-bootx64.efi \
  /usr/lib/systemd/boot/efi/systemd-bootx64.efi.signed \
  /usr/share/systemd/boot/efi/systemd-bootx64.efi \
  /usr/lib/systemd/boot/efi/systemd-bootx64.efi.stub; do
  if [[ -s "$file" ]]; then bootefi="$file"; break; fi
done
ovmf_code=""
ovmf_vars=""
for folder in /usr/share/OVMF /usr/share/ovmf /usr/share/qemu; do
  for pair in 4M normal; do
    if [[ "$pair" == "4M" ]]; then
      candidate_code="$folder/OVMF_CODE_4M.fd"
      candidate_vars="$folder/OVMF_VARS_4M.fd"
    else
      candidate_code="$folder/OVMF_CODE.fd"
      candidate_vars="$folder/OVMF_VARS.fd"
    fi
    if [[ -s "$candidate_code" && -s "$candidate_vars" ]]; then
      ovmf_code="$candidate_code"
      ovmf_vars="$candidate_vars"
      break
    fi
  done
  [[ -n "$ovmf_code" ]] && break
done
if [[ -z "$bootefi" || -z "$ovmf_code" || -z "$ovmf_vars" ]]; then
  echo "AIWS_AB_PRECHECK_FAIL: systemd-boot/OVMF firmware pair not found" >&2
  for folder in /usr/lib/systemd/boot/efi /usr/share/systemd/boot/efi /usr/share/OVMF /usr/share/ovmf /usr/share/qemu; do
    if [[ -d "$folder" ]]; then ls -la "$folder" | head -n 80 >&2 || true; fi
  done
  exit 1
fi
printf 'AIWS_AB_FIRMWARE: loader=%s code=%s vars=%s\n' "$bootefi" "$ovmf_code" "$ovmf_vars"

cp "$ovmf_vars" "$out/ovmf-vars.fd"
xorriso -osirrox on -indev "$iso" -extract /live "$out/live"
kernel="$(find "$out/live" -maxdepth 1 -type f -name 'vmlinuz*' | head -n 1)"
initrd="$(find "$out/live" -maxdepth 1 -type f -name 'initrd*' | head -n 1)"
test -s "$kernel" && test -s "$initrd"
disk="$out/aiws-ab-efi.raw"
truncate -s 512M "$disk"
sgdisk -o "$disk"
sgdisk -n 1:2048:0 -t 1:EF00 -c 1:AIWS_EFI "$disk"
mkfs.fat -F32 -n AIWS_AB --offset=2048 "$disk"
target="$disk@@1048576"
export MTOOLS_SKIP_CHECK=1
for folder in ::/EFI ::/EFI/BOOT ::/loader ::/loader/entries ::/aiws ::/aiws/slot-a ::/aiws/slot-b; do
  mmd -i "$target" "$folder"
done
mcopy -i "$target" "$bootefi" ::/EFI/BOOT/BOOTX64.EFI
mcopy -i "$target" "$kernel" ::/aiws/slot-a/vmlinuz
mcopy -i "$target" "$initrd" ::/aiws/slot-a/initrd
mcopy -i "$target" "$kernel" ::/aiws/slot-b/vmlinuz
mcopy -i "$target" "$initrd" ::/aiws/slot-b/initrd
cat > "$out/loader.conf" <<'EOF'
default aiws-B*
timeout 0
editor no
EOF
cat > "$out/aiws-A.conf" <<'EOF'
title AIWS known-good kernel A
linux /aiws/slot-a/vmlinuz
initrd /aiws/slot-a/initrd
options boot=live components console=tty0 console=ttyS0,115200n8 loglevel=6 aiws.slot=A
EOF
cat > "$out/aiws-B+2.conf" <<'EOF'
title AIWS intentionally broken candidate B
linux /aiws/slot-b/vmlinuz
initrd /aiws/slot-b/initrd
options boot=live components console=tty0 console=ttyS0,115200n8 loglevel=6 panic=3 init=/nonexistent-aiws-init aiws.slot=B
EOF
mcopy -i "$target" "$out/loader.conf" ::/loader/loader.conf
mcopy -i "$target" "$out/aiws-A.conf" ::/loader/entries/aiws-A.conf
mcopy -i "$target" "$out/aiws-B+2.conf" ::/loader/entries/aiws-B+2.conf
echo 'AIWS_AB_TEST: genuine GPT/FAT ESP with UEFI bootloader and A/B entries'
qemu-system-x86_64 -machine q35,accel=tcg -cpu max -smp 2 -m 4096 \
  -drive "if=pflash,format=raw,readonly=on,file=$ovmf_code" \
  -drive "if=pflash,format=raw,file=$out/ovmf-vars.fd" \
  -drive "if=virtio,format=raw,file=$disk" -cdrom "$iso" \
  -nic none -display none -vga std -serial "file:$out/boot-serial.log" &
pid=$!
trap 'kill "$pid" 2>/dev/null || true' EXIT
passed=0
for _ in $(seq 1 550); do
  if [[ -s "$out/boot-serial.log" ]] && grep -q 'AIWS_BOOT_SMOKE_PASS' "$out/boot-serial.log"; then
    passed=1
    break
  fi
  if ! kill -0 "$pid" 2>/dev/null; then break; fi
  sleep 2
done
tail -n 140 "$out/boot-serial.log" || true
if [[ "$passed" != 1 ]]; then
  echo 'AIWS_AB_TEST_FAIL: firmware disk did not recover to guest AIWS Shell' >&2
  exit 1
fi
if ! grep -q 'aiws.slot=B' "$out/boot-serial.log"; then
  echo 'AIWS_AB_TEST_FAIL: no evidence of B boot attempt' >&2
  exit 1
fi
if ! grep -q 'aiws.slot=A' "$out/boot-serial.log"; then
  echo 'AIWS_AB_TEST_FAIL: no evidence of automatic fallback to A' >&2
  exit 1
fi
echo 'AIWS_AB_FIRMWARE_FALLBACK_PASS: B=failed A=recovered OVMF=yes'
