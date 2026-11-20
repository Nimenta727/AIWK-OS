# 2026-11-19 22:48:38 +0800 — V0.1 GitHub publication and hardening

## Summary

- Prepared the initial public repository version of Windows AI Workstation for `Nimenta727/Windows-AI-Workstation`.
- Fixed SQLite connection cleanup and recovery of interrupted background jobs.
- Rejected Windows reserved project names and trailing-dot aliases.
- Resolved absolute Claude/Codex executable paths before starting Windows child processes to avoid project-directory shadowing.
- Added regression tests for path validation, interrupted tasks, CLI launch commands, and portable archive contents.
- Added Windows/Linux CI for Python tests, Windows PowerShell syntax parsing, and portable ZIP artifact upload.
- Added deterministic, source-only portable packaging that excludes credentials and runtime state.

## Files changed

- `aiws/store.py`, `aiws/tools.py`
- `tests/test_core.py`, `tests/test_tools.py`, `tests/test_package.py`
- `scripts/package_portable.py`, `.github/workflows/tests.yml`
- `README.md`, `docs/ARCHITECTURE.md`, `docs/SECURITY.md`
- `docs/routine/2026-11-19_224838-github-publication-hardening.md`

## Verification

- **Passed:** `python -W error::ResourceWarning -m unittest discover -s tests -v` (13/13 on Linux Python 3.13).
- **Passed:** ZIP integrity check with `python -m zipfile -t`.
- **Not yet verified:** native Windows tests, Windows CLI login, Hyper-V PowerShell Direct, PyInstaller build, provider subscription entitlements. Windows GitHub Actions checks run after publishing.

## Known issues

- Prototype routes tasks but does not automate Claude subscription prompts through a third-party API.
- Codex read-only automation is opt-in experimental; sandbox behavior and MCP grants need validation in Windows.
- The development environment cannot access the user's running Hyper-V VM. The ZIP does not include upstream proprietary binaries.

## Next steps

1. Verify the GitHub Actions Windows and Ubuntu matrix and inspect the published portable ZIP artifact.
2. Run `scripts/Preflight-Guest.ps1` in an isolated Hyper-V guest; create a backup/checkpoint.
3. Install Claude Code and Codex through official distributors, log in interactively, and test task handoff.
4. Verify T3 Code and OpenClaw compatibility using published APIs only; add an isolated adapter where supported.
5. Implement durable task queue, cancellation, per-action approvals, and Windows GUI tooling with integration tests.


---

## 历史归档双语概要 / Historical archival synopsis (added 2026-11-20)

- **中文：** 本记录的历史主题为 **github publication hardening**。正文保留当时的变更、测试状态、已知限制和后续计划；这不是对当前版本的重新验收。
- **English:** This dated record concerns **github publication hardening**. Its original changes, verification status, limitations and next steps are preserved; this archival summary is not a new acceptance claim.
- [历史时间索引 / Historical timeline](README.md) · [当前版本 / Current release](../../README.md)
