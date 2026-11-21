# 2026-11-21 13:10 — ISO BIOS/UEFI 原生启动与 AIWS 桌面 Shell

## Changes / 改动
- Added a dedicated ISO firmware boot script that verifies both El Torito
  platform entries and boots from the actual ISO via BIOS/OVMF without
  -kernel/-initrd, with network and host file integration disabled.
- Added separate BIOS and UEFI CI jobs with firmware serial and media
  report artifacts; preserved direct-kernel diagnostics and GPT/ESP A/B.
- Replaced exclusive Chromium kiosk with normal app mode; introduced an
  Openbox-managed XFCE panel and shortcuts for terminal/file manager.
- Added a synthetic live X11 focus and Unicode clipboard check next to
  browser Selenium click/DAG acceptance, and smoke image dependencies.
- Updated static contracts, root/OS README and the OS production gates.

## Files / 影响范围
os/kernel/ci/firmware-iso-boot.sh,
.github/workflows/aiws-os-image-boot.yml,
os/debian/config/includes.chroot/usr/local/bin/{aiws-session,aiws-open-workbench,aiws-boot-smoke},
os/debian/config/includes.chroot/usr/local/share/aiws/shell/openbox.xml,
os/debian/{profiles/smoke.list.chroot,config/package-lists/aiws-desktop.list.chroot},
os/verify/test_config.py, README.md, os/README.md,
docs/README.md, docs/AIWS_OS_PRODUCTION_GATES.md and docs/routine/README.md.

## Verification / 验证
- Code review and static contract coverage prepared.
- This commit does not yet prove that BIOS/UEFI CI or live graphical
  acceptance passed; inspect completed workflow run evidence separately.
- No physical hardware, installer, secure boot, CJK IME, or mandatory
  OS isolation assertion is made.

## Next / 下一步
1. Inspect both real firmware CI runs, fix any evidence-backed failures.
2. Implement a standalone, fail-closed, unprivileged decision service and
   test it with durable DAG state; follow with actual Linux worker isolation.
3. Continue real 2B held-out benchmark and Windows→Linux non-executable
   history migration without weakening their current acceptance gates.
