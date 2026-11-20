# 2026-11-19 23:50 +08:00 — Native WPF reconstruction and visual workflow

## What changed

- Created a new `desktop/AIWorkstation.Desktop` WPF/.NET 10 desktop application with a Claude-inspired but independently designed warm-light, editorial UI.
- Added `desktop/AIWorkstation.Core` for the workflow state machine, templates, step-by-step approval rules, handoff content, workspace validation, official CLI resolution/launch and atomic local storage.
- Added `desktop/AIWorkstation.Core.SmokeTests`, covering stage ordering, approval, retry, handoffs, persistence and workspace checks.
- Added native Windows build script and CI publishing a self-contained `WindowsAIWorkstation.exe` archive.
- Updated the default README to clearly identify native Windows as the primary product; previous Python + web prototype remains available as legacy.
- Added `docs/DESKTOP_REBUILD.md` with architecture, upstream project provenance, licensing, real implemented features, limitations and guest acceptance checklist.

## Sources and legal treatment

- T3 Code (MIT): external companion integration and architecture reference; no code copied.
- OpenClaw Windows Hub (MIT): external companion integration and permissions reference; no code copied.
- Kandev (AGPL-3.0): stage/workflow concepts independently reimplemented; no AGPL code copied.
- Claude Code / Codex: use user-installed official CLI rather than redistributing binary or tokens.

## Verification

- Local WPF builds cannot be run in the current Linux environment without Windows and .NET SDK; Windows GitHub Actions job is the source of EXE compile and packaging verification.
- Existing Python tests remain in the repo. Native core smoke tests run as part of Windows CI.

## Next steps

1. Fix any issues reported by the new Windows CI runner, then verify the executable launches on the actual Hyper-V Windows guest.
2. Build a freeform DAG editor and event-based execution history, with a true integrated terminal where supported.
3. Add isolated Git worktree tasks, permission review and native GUI automation adapters.
4. Add installer signing and support for safe application updates.


---

## 历史归档双语概要 / Historical archival synopsis (added 2026-11-20)

- **中文：** 本记录的历史主题为 **native wpf rebuild**。正文保留当时的变更、测试状态、已知限制和后续计划；这不是对当前版本的重新验收。
- **English:** This dated record concerns **native wpf rebuild**. Its original changes, verification status, limitations and next steps are preserved; this archival summary is not a new acceptance claim.
- [历史时间索引 / Historical timeline](README.md) · [当前版本 / Current release](../../README.md)
