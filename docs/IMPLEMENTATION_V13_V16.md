> **中英导读 / Bilingual overview (2026-11-20)**
>
> 中文：Worktree、Windows 终端、事件账本和 DAG 的实施。本文保留其原始版本背景和测试事实；过往计划、检查或验证不自动代表当前已完成。
>
> English: Worktree isolation, ConPTY terminal, event ledger and DAG implementation. This document preserves its original version context and verification history; earlier plans or results are not automatically current release guarantees.
>
> [文档索引 / Index](README.md) · [最新发行 / Release](RELEASE_NOTES_V19.md)

---

# AIWS V1.3–V1.6 integration / Worktree, ConPTY, Ledger, DAG

> 2026-11-20 · Windows native desktop modules, NOT automatic cloud-model proxying. Source builds on V1.2. Test truth is in GitHub Actions and real Hyper-V validation records; do not infer GUI correctness from CI alone.

## Boundary and product shape

AIWS remains a WPF/.NET 10 Windows EXE hosting **AIWS-owned offline React assets**. The components below share AIWS task IDs, stage IDs and trusted workspace paths. The legacy Python/browser prototype is not a runtime dependency.

| Version | Implementation | Main code | What is *not* claimed |
| --- | --- | --- | --- |
| 1.3 | Native, user-approved Git Worktrees per stage, baseline SHA/branch, stage-specific file scan and Git evidence | GitWorktreeService, WorkstationController, ProjectExplorer, TaskInspector | Git worktree is NOT an OS sandbox or cryptographic proof of AI authorship; no auto-cleanup and no auto-push |
| 1.4 | Windows ConPTY with xterm.js client, user-approved PowerShell session, streamed local VT output, resize/input/close | ConPtyTerminal, TerminalPanel, WPF message bridge | Terminal not available on non-Windows; not an Agent-autonomous shell, no terminal output retention/replay |
| 1.5 | Persisted metadata-only execution ledger with event IDs, stage and run IDs, evidence grade; timeline projection | ExecutionLedger, TaskRepository, ExecutionTimeline | The provider model's inaccessible private request events remain unknown |
| 1.6 | Validated DAG dependencies, independent branches with join, native graph editing, isolated-concurrent-stage gate and dependency-focused handoff context | WorkflowGraph, Models, WorkflowEngine, WorkflowDesigner, DagCanvas, HandoffBuilder | Claude subscription OAuth is not proxied; CLIs are user-confirmed interactive programs, no fake unattended multi-provider execution |

## User workflows

1. Create task > choose **并行 DAG** template; click a stage to inspect dependencies and approval.
2. Create each writing stage's Worktree under the trusted repository's sibling `.aiws-worktrees/` directory after native confirmation. Worktree creation requires a clean source checkout and a valid Git HEAD; it intentionally creates persistent local Git branches. Run only in trusted repositories under a non-admin Windows account.
3. Start an Agent via the explicitly confirmed official Claude Code/Codex CLI launch. Different *running* DAG stages may coexist only if they each have distinct Worktree paths.
4. In **文件与 Git 变更**, select stage to inspect its Worktree, Git status and stage evidence. Approval does not automatically commit or publish changes.
5. Open **Windows 内置终端**, select stage, explicitly approve starting PowerShell in the validated workspace. Input comes only from the current xterm UI. Output stays in volatile memory, never appended to prompt or persistent task events.
6. Open **执行事件账本** for persisted metadata events, with observed/imported/inferred/unknown evidence states. Unknown provider activity is not silently converted to usage=0.

## Trust boundaries

- WebView2 accepts only `https://aiws.local/` messages; native host dispatches fixed action names.
- `worktrees.create` requires native MessageBox confirmation and trusted repository; it is not a general Git shell or file write endpoint. Worktrees are never silently removed.
- `terminal.start` requires native confirmation; subsequent `terminal.write` and `terminal.resize` require the active random session ID. This is a **user terminal**, not an Agent tool. It inherits the Windows account privileges and is not OS-isolated.
- The CLI remains separately installed and authenticated. AIWS does not import OAuth tokens; no default model invocation on opening the UI.
- DAG editing is restricted to not-yet-started tasks; cycles, missing dependencies and unsafe shared-workspace concurrency are rejected.
- The event ledger stores event metadata, not raw terminal contents, model prompts, source files or user credentials. It is a bounded history (2,000 entries per task), not a guaranteed lossless telemetry stream.

## CI and acceptance

- Python legacy tests: 38 local tests, run from repository root.
- Frontend node tests: at least 13 tests, including DAG layers and cycle rejection.
- Native .NET smoke tests: actual Git worktree and existing JSON migration; concurrency gate, DAG editor, ledger persistence, failure handling.
- Windows GitHub Actions: `npm install`, frontend TS/Vite build, WPF/.NET build, core smoke run, self-contained Windows x64 EXE + ui-dist.
- **Pending real Windows Hyper-V guest GUI acceptance**: ConPTY keyboard, resize, Unicode/IME, terminal exit, Git Worktree branch cleanup, user profile ACL, power loss/restart, data migration. CI is not a substitute.

## Engineering debt and next steps

1. Windows interactive ConPTY smoke with actual VM and high-output process; fix any platform-specific pipe/handle lifecycle defects before promoting release as stable.
2. Read-only process-event import from supported structured CLI streams; actual output + tool attribution evidence, without subscription credential proxy.
3. Per-hunk Git review/approval with reversible application; separate isolated Windows tool broker and hardened IPC before allowing Agent-triggered shell commands.
4. Add persisted DAG workflow-definition versions and durable scheduled automatic execution only where official provider interfaces permit; current UI orchestration intentionally uses human-approved handoff.
5. Upgrade migration/backup tests, signing, Windows installer, and security review. Preserve source provenance for T3 Code MIT primitives; do not copy AGPL Kandev source.

Microsoft's [ConPTY guide](https://learn.microsoft.com/en-us/windows/console/creating-a-pseudoconsole-session) and xterm.js MIT license govern the platform integration. Neither component grants OS sandboxing.
