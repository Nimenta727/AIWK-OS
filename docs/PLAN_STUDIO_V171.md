> **中英导读 / Bilingual overview (2026-11-20)**
>
> 中文：计划展示、Markdown 大纲与增量刷新。本文保留其原始版本背景和测试事实；过往计划、检查或验证不自动代表当前已完成。
>
> English: Plan Studio, Markdown outlines and incremental local refresh. This document preserves its original version context and verification history; earlier plans or results are not automatically current release guarantees.
>
> [文档索引 / Index](README.md) · [最新发行 / Release](RELEASE_NOTES_V19.md)

---

# AIWS V1.7.1 — Plan Studio / AI 计划中心

Status: **Windows CI verified** on 2026-11-20 (native run 44708213179; regression run 44708213271); **Hyper-V GUI acceptance remains pending**. This feature was requested after the V1.7 Execution Atlas and does not replace the planned V1.8 Windows capability broker.

## Product objective

AI-produced plans can be long, difficult to follow, and scattered across files. The Plan Studio adds a local-first, structured view of **existing plan documents** and **AIWS workflow progress**. It does not pretend to receive hidden Claude/Codex plan events.

### User interface

Select a task and open **AI 计划中心** (default landing page in V1.7.1). It has:

- **Workflow board**: stage cards grouped into pending/blocked, running, completed and attention states, with dependency state and links to the existing workflow inspector. Percent complete uses persisted AIWS stage status only.
- **Plan document library**: scans specifically named Markdown plans in the task root, `docs/`, `plans/`, `planning/`, `docs/plans/`, `docs/planning/`, `docs/roadmaps/`, `.aiws/plans/`, and `.claude/plans/`. It does **not** scan user home or external provider session directories. Optionally select a stage's existing Worktree rather than the task root.
- **Outline / card board / source**: deterministic headings (levels 1–6), checklists, numbered actions, source text and chapter toggles. Sections and list items are rendered as React text, not interpreted as HTML, and no AI prompt is sent.
- **Progress**: a checked Markdown box is completed; an unchecked box is pending. Plans without checked/unchecked boxes show *unknown* rather than a fabricated 0%.
- **Live refresh**: while this page is active, the native bridge re-reads AIWS workflow state and scans candidate plan-file metadata approximately once every three seconds. A changed file is re-read and the outline re-renders. Users may force-refresh manually; recent detected file changes appear in an ephemeral activity strip. This is **near real-time local polling**, not an instrumented provider stream or persistent file-event history.
- **Navigation**: click a workflow-stage card to inspect its state in the existing workflow page; jump to Execution Atlas for model/context/Git evidence. Markdown bullets are not automatically matched to particular Agent runs without reliable identifiers.

### Core data and trust boundary

`desktop/AIWorkstation.Core/PlanWorkspaceService.cs`:

- Workspace must pass `WorkspaceGuard.RequireTrustedDirectory` and existing relative-path checks.
- Only named plan files in predefined directories are eligible; unrelated Markdown files, `.git`, sensitive filenames and arbitrary caller-supplied locations are refused.
- Reparse points and symlinks in directory chains and individual files are rejected. This is a preflight check, **not an operating-system security sandbox**.
- Maximum 80 discovered plans per workspace, 256 KiB per file; reads reject files that change size or timestamp mid-stream. The frontend limits parsing to 5,000 lines, 180 sections and 1,000 items.
- The bridge has only `plans.list` and `plans.read`; both are read-only and scoped to a previously registered AIWS task or its previously created stage Worktree. No file write, shell, plan execution, provider credential, or general arbitrary file-read action is exposed.
- AIWS does not persist plan contents in its task database. The original Markdown file is the source of truth. Auto refresh is enabled only while Plan Studio is mounted.
- Workflow tasks are read from the existing persistent task state, not guessed from plan prose. No new model calls or token expenditure are required for local display.

### What this feature cannot know

A Claude/Codex plan that exists only in a remote or interactive CLI session, and is not saved into the selected workspace or supplied through an official structured integration, cannot be monitored automatically. The UI does not claim such a capability. Users may direct their AI tool to save a Markdown plan under a recognized project directory to enable near-real-time display, or read existing `docs/ROADMAP.md` files. Worktree vs main-workspace views are explicit; files outside these boundaries are intentionally not scanned.

### Tests and acceptance criteria

- Frontend Node tests include nested headings, checkbox counts, empty plans, non-checklist ambiguity, fenced code, bounded parsing and status/dependency projection.
- Core smoke tests include discovery, relative path traversal denial, unrelated Markdown rejection, sensitive filename rejection, file updates, large document denial, and symlink rejection where the operating system permits fixture creation.
- Existing Python regressions must remain green. GitHub Actions must compile React TypeScript and WPF/.NET, run core smoke tests and package `WindowsAIWorkstation.exe` with the offline `ui-dist/` assets.
- Hyper-V GUI acceptance (not covered by CI): verify multilingual Markdown, a plan actively being written by a real tool, navigation between Worktree and main workspace, a large plan, DPI changes, repeated reload, file permission errors and disconnect behavior.

### Follow-on improvements (not implemented)

1. Controlled paste/import of plans from conversations that do not save Markdown files, with explicit user-approved durable storage and privacy controls.
2. Standardized machine-readable plan schema (`plan.json`) with stable task IDs, dependency edges and progress events where supported provider tooling exposes these.
3. Persistent version diff between plans, superseded plan comparison and task-to-plan-item links (stronger than title similarity).
4. Optional file-system change notification (alongside the polling fallback) and throttled long-document indexing.
5. True streamed provider plan events only through documented, authorized integration; maintain *unknown* for inaccessible internal planning steps.

## Verified build evidence (2026-11-20)

- React/TypeScript, .NET/WPF compile, core smoke suite and Windows self-contained EXE artifact: [Actions 44708213179](https://github.com/Nimenta727/Windows-AI-Workstation/actions/runs/44708213179).
- Repository-wide regression checks: [Actions 44708213271](https://github.com/Nimenta727/Windows-AI-Workstation/actions/runs/44708213271).
- The compiled artifact was inspected in the working environment: it contains `WindowsAIWorkstation.exe`, `ui-dist/index.html`, and the Plan Studio strings in the bundled JS. This does not demonstrate actual Hyper-V GUI behavior.
- The follow-up metadata correction is **also Windows CI verified**: [Actions 44708896256](https://github.com/Nimenta727/Windows-AI-Workstation/actions/runs/44708896256), with regression checks [44708896217](https://github.com/Nimenta727/Windows-AI-Workstation/actions/runs/44708896217).
