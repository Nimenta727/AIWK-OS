# 2026-11-20 00:13 +08:00 — Core smoke test exception handling

## What changed

- Updated `desktop/AIWorkstation.Core.SmokeTests/Program.cs` so its expected-rejection helper handles both `ArgumentException` and `InvalidOperationException`.
- No core logic changed: blank workflow results remain invalid by design.

## Verification

- Windows CI succeeded in compiling the core library, then exposed an incorrect smoke-test expectation for a blank result. This change addresses that test-only failure. Fresh CI pending.

## Next steps

1. Re-run core smoke tests and compile the Windows WPF frontend in Actions.
2. Verify publish creates `WindowsAIWorkstation.exe` and the artifact is downloadable.
3. Run GUI interactions on the Hyper-V Windows guest.


---

## 历史归档双语概要 / Historical archival synopsis (added 2026-11-20)

- **中文：** 本记录的历史主题为 **native smoke test fix**。正文保留当时的变更、测试状态、已知限制和后续计划；这不是对当前版本的重新验收。
- **English:** This dated record concerns **native smoke test fix**. Its original changes, verification status, limitations and next steps are preserved; this archival summary is not a new acceptance claim.
- [历史时间索引 / Historical timeline](README.md) · [当前版本 / Current release](../../README.md)
