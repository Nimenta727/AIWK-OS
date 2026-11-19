# Windows AI Workstation · native desktop edition

**Native Windows EXE, not a localhost webpage.** A new Windows-first AI agent workbench for Hyper-V virtual machines, inspired by the quiet, warm white desktop experience of Claude without copying its assets or product design.

> **V0.4 status:** Windows WPF compilation, core smoke tests and self-contained EXE packaging passed on [GitHub Actions](https://github.com/Nimenta727/Windows-AI-Workstation/actions/runs/44564333810). Download the artifact `WindowsAIWorkstation-Native-win-x64` from that run. The executable is unsigned, and **Hyper-V guest GUI validation is still pending**. This remains a prototype, not a finished or audited operating system agent.

## The new desktop edition

- **Native WPF app:** warm ivory workspace, muted terracotta accent, sidebar navigation, recent projects, stage inspector, task cards.
- **Visual and editable process:** Claude analysis → Codex implementation → Claude review, plus a research workflow template. Edit, reorder, add, approve, complete, retry; data persists locally.
- **CLI availability and launch:** locate separately installed official Claude Code and Codex CLI and start them in a verified workspace after explicit user click; task instructions are copied to clipboard.
- **Agent handoff:** generated prompt includes stage requirements, completed results and `docs/routine` documentation policy. No automated subscription credential handling.
- **Mature platform companions:** optional T3 Code and OpenClaw CLI launch; no upstream source or OAuth material re-bundled.

### Build the Windows EXE **inside the VM**

Install the [Microsoft .NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0) on the Windows guest, clone this repository and open PowerShell:

```powershell
.\scripts\Build-NativeDesktop.ps1
.\dist\native-desktop\WindowsAIWorkstation.exe
```

Alternatively: **GitHub → Actions → Native Windows Desktop EXE → latest successful run → Artifacts → WindowsAIWorkstation-Native-win-x64**. The workflow builds and tests on Windows and packages an unsigned self-contained EXE in a ZIP. This repository does not distribute Claude/Codex executables or tokens.

### What is and is not integrated

The GUI is a native app and orchestrates a **human-supervised** workflow. Each step launches the user's official interactive CLI in its own terminal; **the new desktop edition does not automatically capture the agent's response or execute the whole workflow unattended**. This respects the distinction between the two providers' subscriptions and API access. More information and checklist: [Native desktop architecture and build](docs/DESKTOP_REBUILD.md).

### Previous versions

The V0.1–V0.3 Python + SQLite + browser prototype remains in `aiws/`, `web/`, and its existing scripts for comparison and compatibility. It is **legacy** and **not a runtime dependency** of the native desktop edition. Existing Python data is not deleted or automatically migrated. Old instructions: [Legacy V0.3 operations](docs/V03_OPERATIONS.md).

### Security and development rules

- Run under a standard user on the Hyper-V guest; treat repositories and external prompts as untrusted; back up user files before testing agent actions.
- CLI credentials stay in the providers' own stores; AIWS never imports or stores them. GUI action is required before launching an external program.
- Changes to GitHub projects must include dated modification and next-step records under `docs/routine/`.
- Upstream project licensing and integration constraints are explained in [Desktop rebuild](docs/DESKTOP_REBUILD.md).

**Project license:** MIT for our independently written source. Optional companions remain under their original licenses.
