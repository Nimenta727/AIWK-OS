# 2026-11-21 15:20 — Fix installer preflight Python syntax CI regression

## Evidence and cause
- CI run 44867043892 failed at `python3 -m py_compile os/installer/aiws_install_preflight.py` with `SyntaxError: unexpected character after line continuation character`.
- The preceding commit accidentally inserted literal `\\n` sequences rather than actual newlines in two source lines.

## Change
- Replace both literal escape sequences with actual newlines. No install write paths enabled.
- Preserve disk-signature rejection and preflight fail-closed behavior.

## Verification and next steps
- Failure traced to the exact CI job log; new SHA CI must be rechecked.
- Confirm static contract and Python tests pass, then wait for real firmware ISO boot artifacts.
- Next implement disposable QEMU install acceptance, persisted user-data checks, and boot recovery without host disk access.
