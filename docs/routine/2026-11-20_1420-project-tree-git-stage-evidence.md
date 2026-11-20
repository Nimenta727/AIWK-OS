# 2026-11-20 14:20 (+08:00) — Project tree, Git review and workflow-stage evidence

## What changed / 本次改动

- Built AIWS-native read-only `ProjectWorkspaceService`: file/directory hierarchy, Git porcelain status, staged and working-tree per-file diff, bounded untracked preview, file hashing and HEAD observation.
- Added checkpoint fields to the workflow stage JSON (`GitBefore`, `GitAfter`). Capture happens when the official CLI/manual stage starts and when the user explicitly confirms completion; failures and missing Git remain visible as partial/unknown evidence.
- Added `project.overview`, `project.review`, `project.stageChanges` to the allowlisted local WebView2 bridge with task-scoped paths; repository inspection is **not** a model call.
- Introduced React `ProjectExplorer`: folders, Git badges, side-by-side file explorer and patch view, net commit file lists, stage correlation and evidence-quality warnings. Retained the warm-white AIWS visual language.
- Added read-only Git subcommands and strict path handling (`--literal-pathspecs`, traversal and `.GIT` denial, no link traversal). Changed stage-aware start / completion UI handlers to capture Git evidence before persisting results.
- Preserved existing task JSON and Python/Web workflows; no T3 Code/OpenClaw application shell or provider credentials added.

## Why / 风险与边界

- A Git or filesystem change **observed during** a stage is not proof that a model caused it. UI wording and documentation explicitly separate local evidence from model usage or attribution.
- File content is **not automatically copied into prompts**, saving unnecessary context/Token consumption. Untracked file preview requires explicit selection and excludes sensitive filenames. System-level permissions remain those of the current Windows account.
- Capped output, file tree nodes, changed-file hashes and commit file enumeration; excluded `.git`, junctions/symlinks, and generated directories. Missing/partial results are not represented as zero changes.

## Test / validation

- Local Node pure-model tests: 10/10 passed.
- Legacy Python regression tests: 38/38 passed.
- New Windows core smoke coverage: real Git repository and commits, rename handling, snapshot comparison, file previews, secret-file and path traversal blocking. Windows CI result must be recorded separately; no Hyper-V GUI verification yet.

## Next / 下一步

1. Run native Windows CI, inspect and fix compiler or integration failures before publishing an EXE artifact.
2. Verify explorer/diff/stage ledger with a real repository in the target Hyper-V Windows 11 VM, including large worktrees, odd filenames, DPI and non-admin permissions.
3. Add commit-by-commit provenance and isolated Worktree execution for stronger (but still conditional) attribution; later add approval-gated Git write actions and an application-internal terminal.
4. Keep timestamped documentation in this folder for every subsequent GitHub modification.


---

## 双语历史编目 / Bilingual historical capsule (2026-11-20)

- 中文：本次档案主题为 **2026-11-20 14:20 (+08:00) — Project tree, Git review and workflow-stage evidence**，保留此前变更、测试结果、局限和当时的下一步计划。此追加说明不重新验证历史结论。
- English: This dated record concerns **project tree git stage evidence**. Its earlier changes, tests, caveats and next steps are preserved. This appended synopsis is not a new verification.
- [历史时间线 / Log index](README.md) · [当前发行 / Current release](../../README.md)
