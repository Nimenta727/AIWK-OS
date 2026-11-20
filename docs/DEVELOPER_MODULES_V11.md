# AIWS V1.1: Git review, terminal and Windows capability modules

## Scope and implementation choice

This change brings **code-level modules** into the AIWS-owned desktop frontend and .NET core. There is no dependency on an upstream T3/OpenClaw server, and no AI model invocation is required to display or use the new panels.

| Source of design / code | Upstream review | What has been integrated | Integration boundary |
| --- | --- | --- | --- |
| T3 Code, MIT | `apps/web/src/components/ui/table.tsx` at `8e8ff9b243e5a4c3a837c9033a134b62aac7dade` | Adapted table composition primitives in `T3ReviewTable.tsx` | Removed Tailwind, T3 import paths, RPC and global store dependencies; license preserved in `third_party/t3code/NOTICE.md` |
| T3 Code, MIT | Source control panels, including `DiffPanel` and branch tools | Borrowed separation of read-only Git inspection and explicit write actions | AIWS .NET owns the allowlist and run policy, **not** T3 code |
| OpenClaw Windows Hub, MIT | Permission categories and Windows-node documentation | AIWS-owned capability inventory with explicit human confirmation | No OpenClaw Gateway or node executable included |
| Kandev, AGPL-3.0 | Architecture and task lifecycle | Existing AIWS workflow architecture unchanged | **No AGPL source imported** |

## User experience

Select a task in the desktop sidebar, then **终端与 Diff**:

- **Git 审查**: select one of six predefined *local, read-only* Git views: `status`, `summary`, `diff`, `staged`, `history`, or `branch`. Shows the exact Git subcommand, output, execution time, and truncation state.
- **终端**: open a separate Windows PowerShell window after explicit confirmation. This is not yet a ConPTY/xterm.js integrated pseudo-terminal. The application-internal area is a restricted command/output console; it does not execute arbitrary text.
- **Windows 权限**: inspect capability availability and whether user confirmation is required. This is a read-only report, not an ACL editor or Windows sandbox.

## Core safety architecture

- `GitWorkspaceService.InspectAsync` validates the trusted workspace and maps a fixed view identifier to a constant Git argv array. It does **not** invoke a shell or accept user-provided paths/argv.
- `git --no-pager` is executed directly with `UseShellExecute=false`, `core.fsmonitor=false`, `GIT_OPTIONAL_LOCKS=0`, `GIT_TERMINAL_PROMPT=0`; diffs disable external diff and text conversion.
- Both output streams are drained concurrently, with 120,000 characters of returned stdout, a 12-second deadline, and a concurrency limit of two operations. Output is displayed transiently; never appended to task results or provider request history.
- `WindowsToolPolicy.OpenUserPowerShell` uses the known system PowerShell path rather than looking up an executable in the project folder. An explicit native confirmation and trusted-workspace validation happen first.
- WebView2 still accepts only allowlisted action names from the virtual HTTPS origin `aiws.local`. It does not have general `exec`, `runShell`, `git push`, or elevation endpoints.
- Windows CLI execution remains under the interactive Windows user's privileges. A path allowlist is **not** a security sandbox, so do not work on untrusted repositories using a privileged account.

## Acceptance criteria

1. `npm test` passes seven UI/model tests, including invalid Git view rejection and output-length checks.
2. Existing 38 Python tests pass.
3. .NET core smoke tests pass, including actual temporary Git repository initialization, read-only status collection, rejected `git push` and injected command text.
4. The desktop WPF project and bundled React UI compile on GitHub Actions `windows-latest` and a self-contained EXE artifact is published.
5. In the user's Hyper-V VM, manually verify Git status/Diff, interaction with a real repository, native PowerShell confirmation, and multi-monitor/DPI visual layout. **CI does not replace this VM test.**

## Out of scope / next milestones

- V1.2: native integrated ConPTY session with terminal lifecycle, explicit user input/kill, cancellation, output limits and no agent auto-typing.
- V1.3: structured Diff review (hunks, staged/unstaged distinction, per-file review) without copying file bodies to models.
- V1.4: a separately sandboxed Windows tool-runner process, least-privilege account and auditable per-tool approval tokens.
- Future: distinguish API-available model usage telemetry from interactive CLI internals; no unsanctioned OAuth token forwarding.
