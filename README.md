# Windows AI Workstation · native desktop edition

**Native Windows EXE, not a localhost webpage.** A new Windows-first AI agent workbench for Hyper-V virtual machines, inspired by the quiet, warm white desktop experience of Claude without copying its assets or product design.

> **V0.8 integration status:** new embedded upstream shell requires Windows CI compilation and VM runtime validation. V0.7 core remains intact. Earlier **V0.7 status:** native WPF/.NET compiled and Windows CI [verified successfully](https://github.com/Nimenta727/Windows-AI-Workstation/actions/runs/44657658528), including core smoke tests and x64 single-file EXE publish. This is a prototype, not a finished or audited operating system agent.

## V0.8 — original professional frontend in the Windows EXE

The application now **opens to an embedded original T3 Code or OpenClaw UI** in Microsoft WebView2, rather than a newly hand-drawn imitation. The previously built native AIWS task editor, approvals and request traces remain accessible through **AIWS 任务与流程**.

**Important distinction:** this is the **upstream frontend being hosted from its separately running official local service**, not a copied/forked frontend source tree. T3 Code is deeply coupled to its own React runtime and RPC server. We deliberately did not claim to have transplanted its full source code or merged its task database and token information into AIWS. See [upstream frontend integration and limitations](docs/PROFESSIONAL_FRONTENDS.md).

- Start the official T3 Code local web server on your Windows guest (e.g. with its supported `t3` CLI) or the local OpenClaw Gateway/UI.
- Run `WindowsAIWorkstation.exe`, choose T3 Code or OpenClaw, enter the local HTTP address printed by the upstream service, and click **连接本机服务**.
- Only explicit `localhost`, `127.0.0.1` or IPv6 loopback endpoints are accepted. Third-party remote navigations and new windows are blocked inside the embedded browser; use the system browser for official sign-in.
- The WebView2 Runtime must be present on the guest; it normally ships with recent Windows 11 installations. **Do not enter API tokens into the AIWS URL field.**
- Upstream applications retain independent authorization, state and license. AIWS does not proxy subscriptions or grant OS-level capabilities to an embedded UI.

## V0.7 — execution base stabilization (code-review driven)

The Windows WPF product now uses exclusive local writer leasing, validated/atomic task-store replacement with explicit backup recovery, fail-safe stage preparation, one-time approvals, restart-safe Interrupted states, stricter workspace/PATH checks and sanity checking for imported usage. The UI still launches separately installed official CLI applications (no bundled credentials, no implied model request telemetry). **Windows compilation and Hyper-V GUI validation must be tracked separately.**

See [V0.7 engineering review, evidence and remaining risks](docs/EXECUTION_BASE_REVIEW_V07.md).

## V0.6 — 可视化 AI 请求调用链

新增原生 WPF **调用链画布**（左侧「请求追踪 / Token」），每个任务阶段以五个可点击节点呈现：

**执行器分配 → 上下文准备 → 官方 CLI 启动 → 模型/工具证据 → 结果交接**

- 每个节点都有**计划 / 本地已记录 / 用户导入 / 未知 / 需关注**状态；点击后右侧检查器会显示证据来源、Token 类型与时间范围。
- 导入 Codex JSONL 可看到有序的回合用量及工具启动/完成事件；导入 Claude 结构化 `result.usage` 显示最终汇总。只保存受限数量的事件类型和数值，不保存日志的对话、命令、参数或私密路径。
- **明确限制：** GUI 通过官方交互式 CLI 启动进程，不能直接观察其每一次远程模型请求。导入的结构化 JSON 由用户手动选择，工作台不验证其真实性；未导入的消耗为“未知”，而非零。
- 在重复交接提示词或上下文预估过长时提醒用户确认，避免意外重复启动；这**不是**阻止 CLI 内部 Token 消耗的硬上限。
- 「导出脱敏链路 JSON」只输出阶段序号、执行器、阶段状态和数值统计，不含任务名、工作目录、提示词、模型回复或原始 CLI 日志。
- 保持暖白桌面主题；不需要网页服务器或 API Key，不复制账号令牌。

[请求链路详细设计和验收边界](docs/REQUEST_TRACE.md)

## V0.5 — Request Trace & Token Budget

The native desktop now includes **请求追踪 / Token** in the left navigation:

- Each step records local metadata events (created, approved, started, prompt copied/reused, completed). **Launching an interactive CLI does not expose its internal requests**; these events are not proof a model received a prompt.
- Import a user-selected **Codex `exec --json` JSONL** log or **Claude Code `result.usage` JSON / JSONL** (only use supported/authorized export methods). AIWS stores **only token counts, event type totals, and an import hash**, never raw messages, tool commands, API keys, or CLI session databases.
- Numbers labelled **actual** come from structured provider events; absent usage stays **unknown** rather than zero. Claude cache-read and cache-creation input tokens are normalized into input totals; cached input is a subset, not added again. No claim of financial cost, subscription usage quota, or visibility into providers' private model calls.
- The handoff generator limits prior context to the **last two completed stages**, truncates each prior result to 1,200 characters, deduplicates identical results, and preserves the current task instructions. The displayed token estimate is a **character-based approximation**, not a billable token count or a guaranteed enforcement mechanism.
- Copying an identical handoff twice is marked as a duplicate; **no automatic model call** is made when copying, approving, or preparing the request.

[Request observability design and limitations](docs/REQUEST_TRACE.md)

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
