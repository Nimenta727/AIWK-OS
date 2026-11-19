# Windows AI Workstation — desktop-native V0.4 reconstruction

## Product constraints

1. **Windows executable, not a webpage wrapped as EXE.** WPF and .NET 10, with a native Windows app window. The previous Python web server and browser frontend remain in the repository for historical reference, but are **not launched by the native app**.
2. **Light, warm, quiet design.** Inspiration: Claude Desktop's calm light theme, typography, whitespace, low-contrast borders, and task-focused hierarchy. No Claude logo, asset, CSS, font, or copyrighted screen layout is copied. Our own brand is **atelier · AI Workstation**.
3. **Real editable workflow graph.** Nodes map to persisted state, not fake demonstrations. A selected node has an editor; staged execution is sequential; approval is per node; completion requires a verified human-provided outcome; failure requires a new approval to retry.
4. **Native local storage.** `%LOCALAPPDATA%\WindowsAIWorkstation\tasks.json` and a local backup. No local HTTP port; no OAuth credential imports; no cloud API proxies. Sensitive project contents stay under the user's selected trusted work directory.
5. **CLI integration is explicit.** Detect installed official `claude`/`codex` binaries on PATH without searching the current project directory. The user clicks the Start button; AIWS copies the handoff instruction to clipboard and opens the official interactive executable. AIWS **does not silently inject prompts, automate the Claude subscription, capture model conversations or claim unattended execution.**

## What was adopted from mature projects

| Project | License (verified Nov 19 2026) | V0.4 integration | Code copied? |
|---|---|---|---|
| [T3 Code](https://github.com/pingdotgg/t3code) | MIT | Optional launcher of official installed `t3` CLI; provider separation and project/task layout inspired the design | No |
| [OpenClaw Windows Hub](https://github.com/openclaw/openclaw-windows-node) | MIT | Optional launcher of installed `openclaw` CLI; least-privilege and Windows node permissions guide the roadmap | No |
| [Kandev](https://github.com/kdlbs/kandev) | AGPL-3.0 | Workflow stage orchestration and durable status concepts independently implemented in C#; no Kandev source linked or copied | No |
| [Claude Code](https://code.claude.com/docs) and [Codex CLI](https://github.com/openai/codex) | Official tooling | Launch the user's separately installed and logged-in official commands; not redistributing or credential-wrapping them | No |

This is **functional-pattern migration and external-tool integration**, not wholesale upstream source transplantation. Copying T3's TypeScript or OpenClaw's .NET sources into this WPF app requires additional compatibility analysis and per-file license attribution. Kandev AGPL code must not silently be relabeled MIT.

## Architecture

```
WindowsAIWorkstation.exe  (WPF/.NET, single-file publish)
    ├─ dashboard + native workflow graph UI
    ├─ workflow engine (ordered stages; approvals; recovery)
    ├─ JSON state repository with atomic file replacement + .bak
    ├─ workspace path restrictions and executable allowlist
    ├─ explicit official CLI launcher (Claude Code/Codex)
    └─ optional companion launchers (T3/OpenClaw)
```

V0.4 intentionally does not depend on Python, SQLite, WebView2, WSL2 or Hyper-V internals. It can be used on physical Windows too, but is designed to run in a constrained Hyper-V Windows guest.

## Building

Prerequisites: Windows 10/11 x64 and [Microsoft .NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0). Run in **PowerShell inside the Windows guest**:

```powershell
.\scripts\Build-NativeDesktop.ps1
.\dist\native-desktop\WindowsAIWorkstation.exe
```

For CI go to **Actions → Native Windows Desktop EXE**, run the workflow if necessary, and download the artifact `WindowsAIWorkstation-Native-win-x64` after **all checks pass**. This is a self-contained, unsigned EXE build, **not** an MSI or a code-signed installer.

To use official tools, install them separately using their maintained official installers and sign in as yourself. The native application only detects their executables. An enabled Hyper-V VM checkpoint is a useful test rollback aid, not a replacement for backups.

## Explicit limitations

- Workflow **nodes are editable and sequential**, but the graph is not a freeform drag canvas. Edges are generated from step order. Freeform branches, parallel runs and subagents are future work.
- CLI sessions currently open externally, not as a fully embedded terminal. Automated read-only Codex execution exists only in the **legacy Python prototype**, not this new native application.
- Closing an external CLI is not detected automatically. Operators enter the actual outcome before marking a step complete. Native app reboot retains the last state; a previously running step should be manually checked before completion or failure.
- This release is **not** a unified ChatGPT/Claude conversation client, does not merge memories or accounts, and does not bypass vendor subscription rules.
- Automatic updates, installer signing, Windows GUI automation, unattended Claude orchestration, Git worktree management and comprehensive end-to-end GUI tests are not included in this desktop milestone.

## Review and acceptance on a Windows Hyper-V guest

- [ ] GitHub Actions Windows job builds `WindowsAIWorkstation.exe` successfully.
- [ ] GUI opens directly, **without launching a browser**.
- [ ] Build is verified on Windows 11 guest with standard user permissions.
- [ ] New project in trusted workspace → 3 stages visible.
- [ ] Select step, edit, reorder, save, close/reopen → changes persist.
- [ ] No skipping prerequisite stage or approval.
- [ ] Hand-off copies previous results, without exposing credentials.
- [ ] Uninstalled Claude/Codex shows accurate diagnostic, no silent fallback.
- [ ] Official CLI launches from a trusted workspace after explicit user click.
- [ ] Previous Python deployment remains intact, with no automatic migration or deletion.

## V0.5 next milestones

1. Add an actual freeform DAG visual editor with valid edges, branches, persistent run events, and per-node checkpoints.
2. Evaluate ACP-compatible provider bridges for permitted structured agent events and integrated terminal; do not proxy subscription tokens.
3. Add optional Git worktree creation from the native app with filesystem validation and diff review.
4. Package via an installer with code signing and a verifiable update mechanism; add Windows UI automation tests.
5. Add a separately permissioned OpenClaw Windows node connector, with explicit sandbox/capability confirmations.
