# 2026-11-19 23:05:22 CST — V0.2 workflow and worktree migration

## Changes made

- Added `aiws/workflow.py` with a three-stage Claude → Codex → Claude plan and single-agent templates.
- Added SQLite `workflow_steps`, old-task migration and interrupted-stage recovery without discarding prior work.
- Added stage-by-stage Markdown handoff briefs, provenance, explicit result recording and completion gates.
- Added `aiws/gitops.py` with opt-in user-confirmed per-task Git worktrees for clean trusted repositories.
- Enforced stage-specific interactive Agent selection and prevented manual overwrites of running Codex results.
- Updated browser dashboard to show individual stages, stage controls and isolated Git-worktree actions.
- Updated version, README, architecture, security and upstream licensing decisions.
- Extended Python tests for workflow persistence, migration, state gates, Git worktree isolation and HTTP actions.

## Modified files

- `aiws/__init__.py`, `aiws/server.py`, `aiws/store.py`, `aiws/tools.py`
- `aiws/workflow.py` (new), `aiws/gitops.py` (new)
- `web/app.js`, `web/app.css`, `web/index.html`
- `tests/test_workflow.py` (new), `tests/test_http.py`
- `README.md`, `docs/ARCHITECTURE.md`, `docs/SECURITY.md`, `docs/UPSTREAM_MIGRATION.md` (new)
- `docs/routine/2026-11-19_230522-workflow-worktree-migration.md`

## Testing

- Local Python unittest suite: 19 tests passed on Linux.
- JavaScript parser: `node --check web/app.js` passed.
- GitHub Actions Windows CI and real Hyper-V guest integration are pending after push.

## Limitations

- Architecture patterns migrated as **independent code**; no upstream copyrighted implementation is copied.
- CLI handoff is still human-mediated; no automated Claude subscription proxy.
- Git worktrees isolate Git checkouts but not Windows permissions; do not run on untrusted repositories.
- Native Windows login and PowerShell integration not yet tested against the user's VM.

## Next steps

1. Validate Windows CI and real Hyper-V guest login/worktree experience.
2. Add supported ACP/provider adapter protocol and capability broker with per-tool approvals.
3. Add durable task queue and cancellation without inventing third-party API entitlements.
4. Review T3/OpenClaw APIs and consider optional sidecar connectors rather than bundling whole stacks.


---

## 历史归档双语概要 / Historical archival synopsis (added 2026-11-20)

- **中文：** 本记录的历史主题为 **workflow worktree migration**。正文保留当时的变更、测试状态、已知限制和后续计划；这不是对当前版本的重新验收。
- **English:** This dated record concerns **workflow worktree migration**. Its original changes, verification status, limitations and next steps are preserved; this archival summary is not a new acceptance claim.
- [历史时间索引 / Historical timeline](README.md) · [当前版本 / Current release](../../README.md)
