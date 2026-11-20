# 2026-11-20 01:00 +0800 — V0.5 Request Trace and Token efficiency

## What changed

- Added metadata-only request trace recording to the native desktop workflow.
- Added a warm-white WPF page to review local execution events, request previews, and imported token usage.
- Added optional import of official Codex/Claude structured usage events; no private account credentials or raw conversations are stored.
- Added hash-based duplicate-import suppression and repeated-handoff notifications.
- Reduced unnecessary handoff context to two recent completed steps, 1,200 characters each, without trimming the active task instruction.
- Expanded native smoke tests for normalization, deduplication, persistence, provider mismatch, and context trimming.

## Modified files

- `desktop/AIWorkstation.Core/{RequestTrace.cs,Models.cs,HandoffBuilder.cs}`
- `desktop/AIWorkstation.Desktop/{MainWindow.xaml,MainWindow.xaml.cs}`
- `desktop/AIWorkstation.Core.SmokeTests/Program.cs`
- `README.md`, `docs/REQUEST_TRACE.md`
- `docs/routine/2026-11-20_0100-request-trace-token-optimization.md`

## Validation

- Structured tests added for report statistics, duplicated import, provider mismatch, and persistence.
- Windows CI is the authoritative compiler and executable build check; Linux source environment does not include .NET SDK.
- Real provider CLI logs were not accessed. Token usage remains unknown without explicit import.

## Next steps

1. Confirm successful GitHub Windows build and publish self-contained EXE artifact.
2. Test GUI end-to-end in user's Hyper-V guest with provider-exported logs.
3. Add provider-supported streaming telemetry and user-defined per-stage budgets.
4. Build redacted, shareable request trace export and visual budget trend chart.


---

## 双语归档概要 / Bilingual archive synopsis (2026-11-20)

- **中文：** 历史主题：2026-11-20 01:00 +0800 — V0.5 Request Trace and Token efficiency。保留本文当时的修改事实、测试结论和后续计划，不代表现行发行版重新验证。
- **English:** Historical entry on **optimization**. The original implementation notes, verification outcomes and next steps remain intact; no fresh release verification is implied.
- [历史索引 / Chronology](README.md) · [当前版本 / Current release](../../README.md)
