# 2026-11-19 22:13 — Windows AI Workstation V0.1 initial prototype

## Summary

- Inspected T3 Code, Kandev, and OpenClaw Windows Hub source and licenses.
- Created a standalone Python standard-library local dashboard for a Windows Hyper-V guest.
- Implemented SQLite task database, task handoff to official Claude/Codex CLIs, and deterministic route recommendations.
- Added optional, default-off Codex read-only execution and local-only session security controls.
- Added PowerShell host-to-guest deployment, Windows dependency bootstrap and diagnostics.
- Added an independent tests directory and operations/security documentation.

## Files changed

- `app.py`, `aiws/*.py`, `web/*`, `scripts/*`, `README.md`, `AGENTS.md`, `.gitignore`, `docs/*`, `tests/*`.

## Validation

- Python unit/HTTP tests to be run in current development environment.
- Windows CLI installation and Hyper-V operations **not run**; require test in user's VM.
- No model subscription authentication was attempted or claimed.

## Known limitations

- No Windows executable produced in this environment.
- No T3/OpenClaw internal API adapters yet.
- Claude is launched through official interactive CLI only; not programmatically rerouted via subscription credentials.
- Experiment-only Codex CLI automation with explicit opt-in.

## Next steps

1. Run automated tests and inspect the UI locally.
2. Deploy portable ZIP to a sacrificial Hyper-V Windows test guest and verify PowerShell scripts.
3. Confirm CLI login/entitlements and prompt handoff; test path isolation and rollback.
4. Evaluate supported T3/OpenClaw APIs before writing production adapters.
5. Add Windows GUI broker only after per-action approvals and constrained Windows account testing.


---

## 历史归档双语概要 / Historical archival synopsis (added 2026-11-20)

- **中文：** 本记录的历史主题为 **initial workstation prototype**。正文保留当时的变更、测试状态、已知限制和后续计划；这不是对当前版本的重新验收。
- **English:** This dated record concerns **initial workstation prototype**. Its original changes, verification status, limitations and next steps are preserved; this archival summary is not a new acceptance claim.
- [历史时间索引 / Historical timeline](README.md) · [当前版本 / Current release](../../README.md)
