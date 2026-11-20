# 2026-11-20 02:00 UTC — Native execution base stabilization after code review

## Scope and review

Audited V0.6 native WPF core (task persistence, approval lifecycle, CLI launch, workspace guard, imported-token accounting and trace semantics) against `main` commit `3754e963ecbac4af84c3f0a46b5c012bcd8db614`. Findings and severity are documented in [`docs/EXECUTION_BASE_REVIEW_V07.md`](../EXECUTION_BASE_REVIEW_V07.md).

## Changes made

- Add exclusive local instance/file writer lease and friendly startup error behavior.
- Change JSON writes to staged, flushed, validated replacement with preserved previous backup; require explicit backup restoration and preserve corrupt evidence.
- Add `StageLaunchCoordinator` to separate clipboard preparation, persisted intent, and external process launch. Roll back in-memory stage mutations if the pre-launch commit fails.
- One-shot approval and `Interrupted` state after restart, requiring human verification instead of auto-resuming an unknown CLI session.
- Tighten workspace/path validation and PATH discovery to reject directory links, network shares, user home root and relative CLI lookup entries.
- Normalize token telemetry defensively and reject impossible/malicious measurements.
- Expand native smoke tests with reproducible failure injections; keep legacy Python tests unchanged.

## Verification

- Python regression suite: **38/38 passed** in Linux development environment.
- Native WPF build/smoke: **pending Windows GitHub Actions result at time of initial commit**. The Windows Actions run, not local static inspection, decides whether a binary is usable.
- Hyper-V guest GUI verification: **not yet executed**.

## Next steps

1. Observe Windows CI, resolve compiler/smoke failures, and update this record with final evidence.
2. Test startup recovery, dual-instance lock and CLI preflight on the actual Hyper-V guest.
3. Migrate UI events toward MVVM, implement supported provider event adapters, and add Windows ACL/sandbox enforcement before any unattended agent actions.
4. Evaluate a transactional SQLite task store after backup/recovery semantics are stable.


---

## 双语归档概要 / Bilingual archive synopsis (2026-11-20)

- **中文：** 历史主题：2026-11-20 02:00 UTC — Native execution base stabilization after code review。保留本文当时的修改事实、测试结论和后续计划，不代表现行发行版重新验证。
- **English:** Historical entry on **hardening**. The original implementation notes, verification outcomes and next steps remain intact; no fresh release verification is implied.
- [历史索引 / Chronology](README.md) · [当前版本 / Current release](../../README.md)
