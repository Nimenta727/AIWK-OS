# 2026-11-20 00:11 +08:00 — Windows native CI compiler fix

## What changed

- Fixed two C# CS0201 compilation errors in `desktop/AIWorkstation.Core/AgentTools.cs` by using explicit `Process.Start(...) is null` checks.
- Kept the fixed allowlisted official CLI integration without changing its permissions or token behavior.

## Verification

- First Windows CI build identified CS0201 on the two process-launch lines; this commit is a targeted source fix. New Windows CI run will independently verify it.

## Next steps

1. Inspect the renewed Windows CI build for WPF/XAML errors and fix any incompatibilities.
2. Verify the self-contained native Windows EXE is produced and uploaded as an artifact.
3. Open and run the EXE inside the Hyper-V guest with standard user privileges.


---

## 历史归档双语概要 / Historical archival synopsis (added 2026-11-20)

- **中文：** 本记录的历史主题为 **native ci compiler fix**。正文保留当时的变更、测试状态、已知限制和后续计划；这不是对当前版本的重新验收。
- **English:** This dated record concerns **native ci compiler fix**. Its original changes, verification status, limitations and next steps are preserved; this archival summary is not a new acceptance claim.
- [历史时间索引 / Historical timeline](README.md) · [当前版本 / Current release](../../README.md)
