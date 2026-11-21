> **中英导读 / Bilingual overview (2026-11-20)**
>
> 中文：架构演进和上游设计参考。原有版本背景和测试结论保持原样；本导读不代表重新验证旧版本。
>
> English: Architecture history and reviewed upstream designs. Original version context and verification claims are preserved; this index note does not rerun historical tests.
>
> [文档导航 / Documentation](README.md) · [当前发行 / Current release](RELEASE_NOTES_V19.md) · [历史记录 / Routine](routine/README.md)

---

# AIWS architecture and reviewed code bases

Review date: **2026-11-19**. The official GitHub files below were read via GitHub repository access, not just marketing pages.

| Project | Source examined | Confirmed architecture and application to AIWS | License / constraint |
|---|---|---|---|
| T3 Code | `pingdotgg/t3code/docs/internals/overview.md` (blob `f24e3625d92f8ddeb2a51e8749f8f0a1b84b53dc`) | Provider processes, Git and workspace live on server; authenticated client RPC; separate provider adapters and durable intents; AIWS uses local execution ownership and explicit task state | MIT (`LICENSE` blob `55ee675bb1de9e580b69f3dd68684df2a4dffba7`); no copied code |
| Kandev | `kdlbs/kandev/docs/ARCHITECTURE.md` (blob `db4e9f3923a2c13bda8e69faf34dc17a0f8e1724`) | Go control plane, executor/agentctl, SQLite, event bus and task workflow separation; informs future task engine boundaries | AGPL-3.0 (`LICENSE` blob `be3f7b28e564e7dd05eaf59d64adba1a4065ac0e`); **do not mix its source into a differently licensed distribution without legal review** |
| OpenClaw Windows Hub | `openclaw/openclaw-windows-node/README.md` (blob `565cb408f8bae5fc8d7ee2925e37a6677f3b5796`) | Native WinUI companion, node capabilities, explicit permissions, execution/sandbox controls; AIWS keeps desktop control optional and disabled by default | MIT (`LICENSE` blob `59c39a20a10df4025d7f9c62a1e414c688a30b67`); no copied code |

## V0.3: durable execution control (V0.2 workflow preserved)

```
Local browser 127.0.0.1:8765
    |
    | same-origin HTTP + per-start anti-CSRF token
    v
AIWS Python stdlib control plane
    |-- Router (heuristic recommendation only)
    |-- SQLite tasks, workspace and audit
    |-- Persisted workflow_steps (single / three-stage handoff)
    |-- Task brief Markdown in workspace/tasks/ (previous results are untrusted)
    |-- Explicit, user-approved per-task Git worktree creation
    |-- Windows interactive terminal adapters (Claude/Codex)
    |-- Codex readonly exec (experimental, explicitly opt-in)
    |
    v
Workspace/projects/<slug> (no paths outside canonical projects root)
Workspace/worktrees/T-... (opt-in isolated Git checkout)
```

V0.2 is deliberately modular: `router.py`, `workflow.py`, `gitops.py`, `store.py`, `tools.py`, `server.py`, static UI. It is **not** a copied/forked T3, Kandev, or OpenClaw codebase. It can coexist with them and detect them. **No internal API integration with T3 or OpenClaw has yet been implemented or tested.**

### Credential and model boundary

- Native Claude Code is launched as the unmodified official tool; AIWS does not read or intercept Claude subscription tokens.
- The `codex exec` opt-in pathway uses the user-authenticated Codex binary; it does not extract tokens or convert ChatGPT subscription to a generic API.
- App does not route a request into Claude via OAuth or pretend Claude CLI is an unrestricted third-party API. Add Anthropic API-key-driven integration only as a **separate, explicitly configured module** if needed.
- CLI user identity can differ from GUI user identity; install/login/run under the same Windows user.

### Task state and protocol

Each task now owns one or three persisted `workflow_steps`. A stage must move `pending -> prepared` before its output can be recorded; only `done` unlocks the next stage. `failed` requires re-preparation. Interactive CLI launch does not track the subprocess lifecycle; the human records the true result. The `codex exec` experiment updates only its single stage, and blocks concurrent manual stage completion. Old V0.1 tasks are migrated in place at startup; completed legacy tasks stay completed.

The whole-task state reflects the active stage: `pending -> prepared -> pending` for each approved handoff, then `done` at the end. Worktree creation is a separate explicit action and is allowed only **before** the initial brief. V0.3 adds a durable SQLite queue with one-time approval rows and a single optional worker. Jobs use `queued -> running -> succeeded|failed` (or `cancelled` while queued); a running job becomes `interrupted` after a process restart and is never silently retried. The operator must reconcile any side effects before re-preparing and requesting a new approval. Queued jobs are restored only if the experimental Codex worker is enabled. The worker can run only approved single-stage Codex read-only jobs, never arbitrary commands or a third-party Claude subscription proxy.

### Future iteration

- Add explicit user-initiated cancellation of running subprocess trees and investigate bounded streamed output; the queued job cancellation and crash recovery now exist.
- Add app manifest discovery, version health checks, and signed installer.
- Add explicit adapter contracts to supported T3/OpenClaw APIs, subject to upstream compatibility and licensing.
- Build Windows capability broker with auditable allowlists and per-action human approval.
- Add testing in actual Windows guest + host, including lifecycle/rollback and signing.

## V0.3 approval and execution boundaries

- `aiws/store.py`: `approvals` and `jobs` SQLite tables, one-shot transitions and atomic job/step/task updates.
- `aiws/execution.py`: documented adapter capabilities and optional worker for Codex read-only CLI; no Claude noninteractive subscription proxy.
- `aiws/policy.py`: deny-by-default capability registry; unimplemented shell, network publishing, Windows GUI, file write and administrator operations are not exposed over HTTP.
- `aiws/singleton.py`: cross-platform advisory lock prevents two AIWS servers concurrently opening one workspace.
- `aiws/server.py`: same-origin localhost endpoints for approvals and queue; CSRF required for every decision.
- `web/`: approval center and queued/running/completed job status.

A job **acknowledgement means it was placed in a queue, not that the model completed it**. The approval ID is uniquely bound to one job; repeated approval is rejected. A reboot during a running job is ambiguous and stops for human verification. There is no arbitrary CLI agent prompt endpoint, admin endpoint or desktop GUI controller.
