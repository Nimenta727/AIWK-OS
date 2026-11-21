> **中英导读 / Bilingual overview (2026-11-20)**
>
> 中文：项目文件树、Git 差异和阶段前后检查点。本文保留其原始版本背景和测试事实；过往计划、检查或验证不自动代表当前已完成。
>
> English: Project file tree, Git differences and stage checkpoint evidence. This document preserves its original version context and verification history; earlier plans or results are not automatically current release guarantees.
>
> [文档索引 / Index](README.md) · [最新发行 / Release](RELEASE_NOTES_V19.md)

---

# V1.2 · Project structure, Git evidence and stage correlation

## Goal

The AIWS workstation needs to connect a conversation / Agent workflow to **observable work on the actual project**: file hierarchy, Git status, per-file patches, commits and which stage was active when a change was observed. This is the first **read-only evidence** implementation, not an editor, git staging/pushing tool, or an Agent-author attribution engine.

## User interface

New `文件与 Git 变更` navigation in the AIWS-owned React UI (`desktop/AIWorkstation.Frontend`). The view includes:

1. **Project tree**, based on the selected trusted local workspace, with collapsible folders, Git status badges, skipped generated/huge directories and explicit truncation notices. Does not traverse directory symlinks / junctions. Files are read-only.
2. **Git per-file review**. `git diff -- <literal path>` and staged `git diff --cached -- <literal path>` are shown with separate headings and color-coded lines. Output is bounded; staged/working-tree changes cannot be silently conflated. For explicitly selected, small, supported, untracked text files, a bounded preview is shown; probable secret files are never previewed.
3. **Stage change ledger**. At stage start, capture HEAD and bounded Git porcelain statuses with file fingerprints. At stage completion, capture another checkpoint. While Running, compare against a fresh read-only snapshot only on user request. The UI can also show **paths changed by commits** between the recorded HEADs.
4. **Provenance and interpretation**. The ledger says **changes observed between stage checkpoints**, never "written by Claude/Codex" without stronger evidence. If Git is unavailable, the repo is too large, hashes cannot be read or history has changed, report **partial / unknown**, not zero changes.

## Data and bridge

- AIWS .NET `ProjectWorkspaceService` owns inspection, parsing and checkpoint comparison. `GitWorkspaceService` owns the Git executable allowlist and subprocess constraints. No user-supplied shell command, Git write command, remote network fetch, `.git` traversal or unrestricted editor endpoint.
- WebView2 RPC actions: `project.overview`, `project.review`, `project.stageChanges`, only for an existing AIWS task and validated relative paths. All results are rendered as **React text**, never HTML injection.
- `WorkflowStep.GitBefore` and `WorkflowStep.GitAfter` persist **file path, Git status and content hash**, not full file bodies. Pre-existing task JSON remains compatible; absent checkpoints render as missing evidence.
- `CaptureAsync` hashes up to 2 MB per changed/untracked file, limited to 800 Git entries; larger files receive an approximate size + mtime signature. The scanner caps the tree at 2,500 items and depth 10, skips `.git`, generated dependency directories and reparse points.
- No file text, diff, Git checkpoint, or stage ledger is **automatically appended to an Agent prompt**. Existing `HandoffBuilder` is unchanged. Reading local Git metadata does not itself cause model token usage.

## Security and technical limitations

- This is **not an OS sandbox**. Git and CLIs still run under the current Windows account. Do not open unknown repositories as administrator.
- Git diff contents might include secrets already committed to the repository. They are displayed locally when explicitly selected; do not copy/paste blindly into a model.
- A live user or other program can modify files while an Agent stage is active; temporal correlation does not prove causality. Changes created and reverted before the next snapshot might be invisible. Full provenance needs instrumented tool events or isolated worktrees with tracked process identities.
- A commit changing HEAD is reported independently of the working-tree status. The file list from `git diff --name-status -z <old> <new>` covers the net change between commits, not each intermediate commit.
- This version does not implement automatic git add, commit, push, code execution, shell commands, code editing, change approval or real-time filesystem watcher. Those would need explicit authorization gates, event recording and a separate safe execution boundary.
- Git snapshots are metadata evidence, not a versioned copy of every file. Use Git itself and external backups for data recovery.

## Verification

- Native smoke suite: Git porcelain -z parsing including renames; path traversal and `.GIT` denial; real temporary Git repo, edits, untracked preview, secret-file denial, committed-file comparison; stage checkpoint comparison, caveat text and read-only behavior.
- UI Node tests: status labels, no model attribution in change labels, non-fabricated commit identifiers. Previous Python 38 tests retained.
- GitHub Windows CI: `npm test`, frontend build, WPF compilation, .NET core tests, Windows EXE ZIP packaging. Hyper-V GUI verification remains a separate manual acceptance gate.

## Future work

1. Full **commit history timeline** (individual commits rather than net-HEAD comparison), cross-linked to tasks with stronger evidence.
2. Git review controls: staged changes and patch approval with per-operation confirmation and rollback, never implicit push.
3. Read-only live filesystem event stream with identity limits; use isolated worktrees for more reliable Agent attribution.
4. Optional code map (symbols, relationships) and language-server indexing without sending source files to remote models.
