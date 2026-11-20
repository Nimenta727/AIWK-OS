# 2026-11-19 22:52 +0800 — Initialize Windows AI Workstation repository

## What changed

- Created the initial GitHub repository history in an empty `main` branch.
- Prepared for publication of the Windows AI Workstation V0.1 prototype and its source, tests, and Hyper-V deployment scripts.
- Kept upstream Claude Code and Codex binaries out of Git; installation happens through official package managers with user login.

## Modified files

- `docs/routine/2026-11-19_2252-repository-bootstrap.md`

## Verification

- GitHub repository is empty before bootstrap; account has write access.
- The prototype passed 13 local Python unit/integration tests; GitHub Actions validation pending source push.

## Next steps

1. Publish portable dashboard source, scripts, tests, and documentation.
2. Verify Windows and Linux CI and the portable ZIP artifact.
3. Install and test on the user's Hyper-V guest with official Claude/Codex login.
4. Develop supported Agent adapters and a durable orchestration queue.


---

## 历史归档双语概要 / Historical archival synopsis (added 2026-11-20)

- **中文：** 本记录的历史主题为 **repository bootstrap**。正文保留当时的变更、测试状态、已知限制和后续计划；这不是对当前版本的重新验收。
- **English:** This dated record concerns **repository bootstrap**. Its original changes, verification status, limitations and next steps are preserved; this archival summary is not a new acceptance claim.
- [历史时间索引 / Historical timeline](README.md) · [当前版本 / Current release](../../README.md)
