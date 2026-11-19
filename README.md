# AIWS · Windows AI Workstation (V0.2)

> A runnable **prototype**, not a finished or audited Windows AI operating system. Built for a Windows 10/11 guest running in Microsoft Hyper-V.

**What works in V0.2**: staged dual-agent workflows (Claude analysis → Codex implementation → Claude review) with SQLite step persistence, explicit per-step approval and handoff summaries; user-confirmed isolated Git worktrees for clean trusted repositories; plus V0.1 features: a localhost-only browser dashboard, isolated project directory selection, SQLite tasks, deterministic agent recommendations, task briefs for agent handoff, detection of local Claude/Codex/T3/OpenClaw CLIs, interactive Claude/Codex terminal launch on Windows, and **opt-in experimental** Codex read-only analysis with result capture. Includes Hyper-V host→guest copy script, WinGet/bootstrap scripts, unit/HTTP tests, source audit, and `docs/routine/`. GitHub Actions runs Python tests on Windows and Linux, validates PowerShell syntax on Windows, and produces a source-only portable ZIP artifact.

**Not implemented**: fully automatic Claude subscription orchestration, OS-wide GUI automation, unified ChatGPT/Claude chats and memories, unattended administrative operations, integration with T3 Code/OpenClaw internal APIs, or a precompiled/signed Windows executable. The packaged ZIP contains **our code and installer scripts only**; it does **not** redistribute Claude Code, Codex or account tokens.

## 1. Preferred install (inside the Windows guest)

Download the portable ZIP from the repository’s **Actions → Python & Windows checks → Artifacts → AIWS-Windows-Portable** (after a successful workflow), or package it locally with `python scripts/package_portable.py`. Transfer the ZIP into the VM and extract to a folder such as `C:\AIWS\AIWS-Prototype`.

Open a PowerShell **in the Windows guest**, run:

```powershell
cd C:\AIWS\AIWS-Prototype
.\scripts\Preflight-Guest.ps1
.\scripts\Install-Guest.ps1 -CreateWorkspace -InstallTools
# Optional: .\scripts\Install-Guest.ps1 -InstallT3
```

WinGet and npm install the **official third-party products from their respective sources** (network required). After installation, **close and reopen PowerShell** to refresh PATH. Log into the official programs yourself:

```powershell
claude
codex login
```

Then start the local dashboard:

```powershell
.\scripts\Start-AIWS.ps1
```

Open `http://127.0.0.1:8765` from the **guest**. Create a project under `projects`; initialize Git with `git init` or clone your repository to that folder. Create a task; for a dual-agent task, AIWS now creates a **three-stage plan**: Claude analysis → Codex implementation/testing → Claude review. For an existing *clean and trusted Git repository*, optionally click **新建隔离 Git 工作区** before preparing the brief. Then:

1. Click **生成当前阶段交接文档** (creates `tasks/T-....md` and a stage-specific archive).
2. Click the button to launch **only the stage's designated official CLI**, or launch one of the CLIs for a manually routed step.
3. Follow the brief's saved path in the terminal; **AIWS does not automatically inject the prompt**, proxy subscription credentials, or grant the CLI OS privileges.
4. Return to the dashboard and enter an **actual result summary** in the stage form. Mark that stage done to unlock the next stage, or failed to request re-preparation. Past results are passed to the next brief as **untrusted context**, not as system instructions.

A Git worktree stays under `AI-Workstation/worktrees/T-...`; it has its own `aiws/t-...` branch. AIWS intentionally does **not** automatically merge or delete it. Review changes and merge/remove worktrees through normal Git workflows after testing. Worktree creation requires explicit confirmation and is disabled on dirty repositories.

### Experimental read-only Codex execution

After testing the official CLI in an ordinary account, optionally start with:

```powershell
.\scripts\Start-AIWS.ps1 -EnableCodexReadonly
```

This makes the **Codex 只读分析** button available **only for single-stage Codex tasks**. It requires explicit per-task confirmation, a Git-initialized project, a local CLI login, and invokes `codex exec --sandbox read-only --ephemeral -` with the prompt via **stdin**. It captures the output to SQLite, stops after 300 seconds, and does not intentionally edit files. **Warning:** repo-defined MCP tools and external side effects can exceed this sandbox boundary, and native Windows sandbox behavior varies by CLI version. Only test on trusted repositories; do not infer from this feature that the VM is hardened against arbitrary agent commands.

### 2. Hyper-V host-assisted copy (optional)

Run the following on the **Hyper-V host** in an elevated PowerShell. This uses **PowerShell Direct**, requires a running **Windows** guest and its credentials, and does not expose any network endpoint:

```powershell
.\scripts\Deploy-HyperVHost.ps1 -VMName 'YOUR-VM-NAME' -ZipPath 'C:\path\AIWS-Prototype.zip'
```

The guest code lands in `C:\AIWS\AIWS-Prototype`. This is a **copy, not an unattended install**. Enter the VM normally and finish setup/login there. The helper refuses to overwrite an existing deployed directory. To redeploy, first back up/rename that directory. The SQLite workspace is in `%USERPROFILE%\AI-Workstation` and is separate from the code folder.

### Optional Windows `.exe` build

`./scripts/Build-Windows.ps1` installs PyInstaller from PyPI and makes an **unsigned local Windows build** in `dist/`. This build script has not been run on a Windows VM here. Do not distribute an unsigned binary as if it were officially released. The portable Python version is the primary verified artifact.

## 3. Why no bundled Claude/Codex binaries?

The installer resolves the upstream tools directly, and the user performs official login. Bundling proprietary binaries or repackaging subscription OAuth tokens would introduce update, integrity, redistribution, and authorization risks. Anthropic explicitly restricts routing third-party app requests through a Claude subscription. AIWS does not proxy Claude OAuth or read Claude credentials. The interactive Claude shell is launched as an unmodified user-owned program. Codex's documented noninteractive CLI supports a controlled, opted-in invocation.

## 4. Security principles

- HTTP binds **only** to `127.0.0.1`; DNS rebinding host validation and per-start CSRF token are checked.
- No arbitrary shell / PowerShell action endpoint, no remote connections, no system installer triggered from the browser.
- Project slug and canonical path are validated; project paths outside the managed root are rejected.
- Script install only when an operator runs `-InstallTools` or `-InstallT3`.
- Audit metadata is written to local `logs/audit.jsonl`; raw OAuth/API tokens are not requested.
- A VM snapshot is helpful for rollback but is **not** a backup and not a complete security isolation boundary.
- Your CLI's own permissions, MCP settings, account entitlements and provider terms still apply.

Read [Architecture](docs/ARCHITECTURE.md) and [Risk Controls](docs/SECURITY.md) before enabling extra permissions.

## 5. Project layout

```
AIWS-Prototype/
├── aiws/                 # Stdlib backend, staged workflows, Git worktrees, routing, SQLite, CLI adapters
├── web/                  # Offline browser UI
├── scripts/              # Hyper-V + Windows setup, optional packaging
├── docs/ARCHITECTURE.md # Reviewed upstream source references
├── docs/SECURITY.md     # Scope and risk register
├── docs/routine/         # Timestamped project change logs
├── tests/                # Python unit + HTTP integration tests
├── AGENTS.md             # Agent modification and routine rules
└── app.py                # Start point
```

## 6. Development/test

No third-party Python dependencies are required to run the portable version. CI runs this suite on Windows and Linux; local execution here only verifies Python, not the real Hyper-V Windows guest:

```powershell
python -m unittest discover -s tests -v
python app.py --no-browser --workspace .\dev-workspace
python scripts/package_portable.py --output ..\AIWS-Prototype.zip
```

For a new feature, modify the project, add tests, and create `docs/routine/YYYY-MM-DD_HHMMSS-summary.md` listing what changed, validation results, and next steps.

## Verified upstream docs/source

- Upstream feature assessment and non-copy policy: [migration notes](docs/UPSTREAM_MIGRATION.md)
- T3 Code architecture and install: https://github.com/pingdotgg/t3code/blob/main/docs/internals/overview.md
- Kandev architecture (AGPL-3.0): https://github.com/kdlbs/kandev/blob/main/docs/ARCHITECTURE.md
- OpenClaw Windows Hub (MIT): https://github.com/openclaw/openclaw-windows-node
- Claude Code Windows installation and terms: https://code.claude.com/docs/en/setup and https://code.claude.com/docs/en/legal-and-compliance
- Codex noninteractive CLI: https://learn.chatgpt.com/docs/non-interactive-mode
- Hyper-V PowerShell Direct: https://learn.microsoft.com/en-us/windows-server/virtualization/hyper-v/powershell-direct

This release independently implements selected upstream-inspired capabilities; it does **not** vendor upstream source files. Direct source copying must retain license notices and pass a separate compatibility review. See `docs/UPSTREAM_MIGRATION.md`.
