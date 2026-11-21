# 2026-11-21 14:50 — Alpha 0.1 installer preflight and Shell 2.0 increment

## Changed / 本次改动

- Added `docs/AIWS_OS_ALPHA_PLAN.md` with M1–M4 dependencies, hard acceptance criteria, and strict release claims.
- Added `os/installer/aiws_install_preflight.py`: read-only VM/UEFI/lsblk inspection and explicit refusal of `--install`; no partition, format, EFI write or host disk modification.
- Added `os/installer/README.md` and `os/verify/test_installer_preflight.py` covering invalid disks, removable/mounted/partitioned media, minimum size, and fail-closed install requests.
- Extended both full and smoke Debian profiles with xfce4-appfinder, xfce4-notifyd and Fcitx5 Chinese input packages.
- Extended Openbox keyboard shortcuts (launcher, terminal, files, browser, IDE, window switching) and session startup with optional notification/input method startup.
- Added Shell contract tests to `os/verify/test_config.py`, syntax preflight to static workflow and synchronized root/OS/docs indexes.

## Validation / 验证边界

- Code and contract tests are committed; CI must be checked on this SHA after publication.
- No disk installer was enabled; no A/B snapshot or rollback implementation is claimed.
- Static package/shortcut tests are not GUI acceptance or actual Fcitx5 Chinese IME verification.
- Existing same-UID Broker is **not** mandatory isolation; M3 and M4 are not completed.

## Next steps / 下一步

1. Create disposable qcow2 + OVMF installation integration harness; design explicit interactive disk authorization and reproducible install image.
2. Implement system/user-data separation and A/B update rollback, then inject boot failures and verify recovery.
3. Complete Shell GUI keyboard/IME/click acceptance and native application discovery.
4. Add separate UID + MAC confined Worker, then full Agent plan/execute/verify benchmarks.
5. Record all CI results, failures and release gates in subsequent routine entries.
