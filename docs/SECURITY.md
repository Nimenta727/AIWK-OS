# Security scope and rollout gates

**Scope:** private experimentation on a Hyper-V Windows guest with existing Claude and ChatGPT subscriptions. This is an **early prototype**, not an agent containment product.

## Baseline

1. Snapshot only after making an independent backup; snapshots may not protect against all corruption and can grow substantially.
2. Use an unprivileged Windows user with access only to dedicated AIWS projects. Never run the dashboard elevated.
3. No shared host drive, no automatic host credential passthrough, no LAN-accessible control endpoint.
4. Run CLI installs and OAuth login yourself; never share the resulting auth files or tokens.
5. Treat README/issue/browser content as untrusted; ignore tool instructions embedded in that content.
6. Keep an outbound network policy appropriate to your projects. `read-only` does **not** imply no network communication.
7. Never assume Claude Code native Windows operations are sandboxed: its official docs distinguish native Windows and WSL2 sandbox support.

## Safeguards present

- Localhost-only listener, minimal endpoint surface, host and origin filtering, anti-CSRF for POST, no CORS headers, restrictive CSP.
- No endpoint to execute arbitrary user-provided commands.
- Task descriptions have length limits; project paths are rooted and canonicalized.
- Codex opt-in defaults OFF, uses read-only sandbox, no untrusted prompt in Windows command-line arguments, bounded timeout.
- No automatic git push, package install, admin elevation, VM snapshot or GUI control from dashboard.
- Worktree creation requires explicit opt-in and a clean Git root; path, branch, and command arguments are controlled by AIWS. Trust the repository before granting Git operations: repository Git configuration/filters can still execute other programs.
- Staged workflows cannot skip a step by calling the completion API. Manual workflow completion is disallowed while a background Codex worker is running. Previous-stage outputs are explicitly labeled untrusted data.

## Known limitations requiring validation

- A process run as the same Windows account can access resources of that account. **AIWS does not provide OS-level sandboxing.**
- A compromised local process can inspect local state; localhost binding alone is not sufficient protection from malicious software in the guest.
- Codex project MCP configurations can grant additional capabilities; only use known trusted repositories with experimental mode.
- Python HTTP service and local processes have not been pen-tested or load-tested.
- CLI / WinGet ID stability and installer behavior must be verified inside the real VM, especially after software updates.
- In-process daemon threads are not a durable queue; on restart formerly `running` tasks are marked `failed`; job results still require manual reconciliation.
- Project names use a Windows-compatible restricted set but NTFS reparse points and special filesystem conditions still require security review.
- T3/OpenClaw API integration, WSL2 and GUI automation are not implemented. The new workflow and worktree features are independent, not upstream code copies.
- Git worktrees are not OS sandboxes; a CLI may still read other files available to the same Windows user. Worktree operations can invoke Git filters configured by a repository, so only create them from trusted projects.
- End-to-end Windows GUI behavior, CLI OAuth status, and git-worktree ACLs still require testing in the actual Hyper-V VM.

## Acceptance gates before expanding permissions

- P0: Hyper-V guest snapshot, independent backup, non-admin user, VM configuration known.
- P1: CLI binary versions, account login, no accidental API-key fallback.
- P2: AIWS tasks created, prepared and launched locally, no external port listening.
- P3: Two independent project paths, traversal blocked, tasks persist after restart.
- P4: Test Codex read-only mode on *trusted* Git repo, verify no source diffs and permission controls.
- P5: Any GUI/system-edit features require per-action approval, allowlists, independent Windows integration tests, and rollback demonstrations.

## Provider policies

Use the current official documentation before automating provider access. Anthropic's legal guidance says subscription OAuth is intended for normal native Claude apps and prohibits developers from routing third-party requests through subscription credentials. Codex `exec` is documented for scripting but its exact authentication mode, rate limits, and Windows sandbox behavior depend on the installed version.
