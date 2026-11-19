# AIWS architecture and reviewed code bases

Review date: **2026-11-19**. The official GitHub files below were read via GitHub repository access, not just marketing pages.

| Project | Source examined | Confirmed architecture and application to AIWS | License / constraint |
|---|---|---|---|
| T3 Code | `pingdotgg/t3code/docs/internals/overview.md` (blob `f24e3625d92f8ddeb2a51e8749f8f0a1b84b53dc`) | Provider processes, Git and workspace live on server; authenticated client RPC; separate provider adapters and durable intents; AIWS uses local execution ownership and explicit task state | MIT (`LICENSE` blob `55ee675bb1de9e580b69f3dd68684df2a4dffba7`); no copied code |
| Kandev | `kdlbs/kandev/docs/ARCHITECTURE.md` (blob `db4e9f3923a2c13bda8e69faf34dc17a0f8e1724`) | Go control plane, executor/agentctl, SQLite, event bus and task workflow separation; informs future task engine boundaries | AGPL-3.0 (`LICENSE` blob `be3f7b28e564e7dd05eaf59d64adba1a4065ac0e`); **do not mix its source into a differently licensed distribution without legal review** |
| OpenClaw Windows Hub | `openclaw/openclaw-windows-node/README.md` (blob `565cb408f8bae5fc8d7ee2925e37a6677f3b5796`) | Native WinUI companion, node capabilities, explicit permissions, execution/sandbox controls; AIWS keeps desktop control optional and disabled by default | MIT (`LICENSE` blob `59c39a20a10df4025d7f9c62a1e414c688a30b67`); no copied code |

## Current V0.2

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

The whole-task state reflects the active stage: `pending -> prepared -> pending` for each approved handoff, then `done` at the end. Worktree creation is a separate explicit action and is allowed only **before** the initial brief. There is still no durable external subprocess queue: after restart, `running` tasks/steps are marked `failed`, and the operator must reconcile any external side effects.

### Future iteration

- Extract persisted job executor with cancellation and recovery.
- Add app manifest discovery, version health checks, and signed installer.
- Add explicit adapter contracts to supported T3/OpenClaw APIs, subject to upstream compatibility and licensing.
- Build Windows capability broker with auditable allowlists and per-action human approval.
- Add testing in actual Windows guest + host, including lifecycle/rollback and signing.
