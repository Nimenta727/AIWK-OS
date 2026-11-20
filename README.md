# AIWS V1.8.1 — Studio frontend / 视觉与交互可靠性优化

本次迭代重构了 Windows 桌面 UI：深色专业侧栏、暖白工作区、清晰的卡片层次、可搜索任务、键盘快捷键、可访问弹窗、仅在流程页显示的阶段检查器，以及统一的本地操作反馈。修复防重复提交、过期状态响应、计划绑定与终端快速输入的桥接压力；全部工作仍在本地，不增加模型请求。**真实 Hyper-V GUI 与 WebView2 行为须独立验收。**

- [完整 UI/交互设计与验证边界](docs/UI_STUDIO_V181.md)
- [本轮开发日志与后续安排](docs/routine/2026-11-20_2003-studio-frontend-interaction-hardening.md)

---

# AIWS V1.8 preview — Agent 调度、统一总控台、可靠性加固

**V1.8 Windows CI 已验证（2026-11-20）**：Node 前端 29/29、.NET 核心 smoke、WPF 编译、自包含 EXE 和离线 UI 打包全部通过。[原生 Windows CI #44729416838](https://github.com/Nimenta727/Windows-AI-Workstation/actions/runs/44729416838) · [Python/Windows 检查 #44729416839](https://github.com/Nimenta727/Windows-AI-Workstation/actions/runs/44729416839)。**Hyper-V GUI、独立权限 Broker、代码签名与无人值守 Agent 执行尚未验收。**


已接入第 4–6 阶段的**可验证核心能力**：DAG 就绪计算、经审批的持久化调度队列、执行器可用性建议、统一计划/调用/Git 总控视图、写操作串行化、脱敏诊断导出和 Hyper-V 发行包只读预检。UI 入口：**AI 协作总控台**。

重要限制：队列**不会自动发起 Claude/Codex 请求**；CLI 仍需用户通过 Windows 原生确认。没有完成独立权限 Worker、无人值守官方适配器、签名安装器以及 Hyper-V GUI/ACL 验收，**不是正式 V2.0 稳定版**。技术说明：[UNIFIED_ORCHESTRATION_V18.md](docs/UNIFIED_ORCHESTRATION_V18.md)，开发记录：[routine](docs/routine/2026-11-20_1910-phases-4-5-6-orchestration.md)。

---

# AIWS — Unified Task Core · Context Compiler · Provider Adapters (V1.7.3)

**Windows CI verified:** [Native Windows EXE #44717741460](https://github.com/Nimenta727/Windows-AI-Workstation/actions/runs/44717741460) and [Python/Windows regression #44717741422](https://github.com/Nimenta727/Windows-AI-Workstation/actions/runs/44717741422) passed. Hyper-V real-GUI verification is still pending. See [verification routine](docs/routine/2026-11-20_1820-unified-core-windows-ci-verified.md).

The first three foundational phases of AIWS's unified Agent control plane are implemented: **one durable task**, explicitly linked Markdown plan hashes, stable per-stage work items and artifact references, a deterministic context compiler with provenance, and capability-aware switching between separately installed Claude Code/Codex CLIs. UI: **可视化工作流 → 统一任务档案 / 阶段检查器** and **AI 计划中心 → 绑定此计划版本**.

**Windows permission Broker remains a future V1.8 milestone.** This V1.7.3 task foundation does not change that security roadmap.

**No autonomous model routing is claimed.** Interactive CLI launch still requires Windows confirmation; an AIWS-local launch record does not prove a model request, and approximate handoff size is not provider token billing. See [implementation/acceptance notes](docs/UNIFIED_TASK_IMPLEMENTATION.md) and [change log](docs/routine/2026-11-20_1810-unified-task-context-provider.md). Windows CI and the real Hyper-V GUI test must be tracked independently.

---

# AIWS V1.7.2 — Token-aware local handoff preflight

> **产品核心：统一 Agent 任务控制平面，而非多模型聊天启动器。** 任务、计划、上下文、模型切换、Git 变更和调用证据必须共享同一套状态。详见 [统一 Agent 控制平面设计](docs/UNIFIED_AGENT_CONTROL_PLANE.md)（设计目标，非已完成自动调度）。

New tasks default to a **lean single-Agent + human-review** workflow. Before launching an official interactive CLI, AIWS previews the *estimated* size of its own handoff prompt and prevents over-limit or unconfirmed duplicate launches **before copying to the clipboard**. Per-task warning/stop estimates can be configured in the stage inspector; the default is 2,500 / 6,000 estimated tokens. This is **not a provider-side token cap** or a claim to observe all internal CLI usage. Reading plans, files, Git and execution graphs does not call a model.

See [V1.7.2 context and budget design](docs/TOKEN_EFFICIENCY_V172.md) and [routine record](docs/routine/2026-11-20_1745-context-budget-preflight.md). Continue to use `ui-dist/` alongside the Windows EXE. Hyper-V GUI acceptance remains pending.

---

# AIWS V1.7.1 — AI 计划中心 / Plan Studio

新增 **AI 计划中心**：将 AIWS 工作流阶段与项目 Markdown 计划书展示为分层大纲、任务看板和原文，包含清单完成度、依赖/执行状态及每 3 秒的本地近实时刷新。选择不同 Agent Worktree 可查看对应计划文档；打开页面不会发送模型请求，也不会自动扫描供应商账号会话目录。CLI 内部未保存成文件的计划无法自动监控。Windows 原生 CI 已通过：[编译与核心测试](https://github.com/Nimenta727/Windows-AI-Workstation/actions/runs/44708213179)、[回归检查](https://github.com/Nimenta727/Windows-AI-Workstation/actions/runs/44708213271)，Hyper-V GUI 实机验收尚未进行。参见 [计划中心技术设计](docs/PLAN_STUDIO_V171.md) 和 [开发记录](docs/routine/2026-11-20_1705-plan-studio-live-markdown.md)。

---

# AIWS V1.7 — AI 调用与项目结构双向可视化 / Execution Atlas

**新增默认页面：AI 调用与结构。** 左侧展开任务、阶段、上下文和导入的模型/工具事件；右侧对比阶段修改前后的项目目录结构，点文件可看 Git Diff，并从文件反查关联阶段。读取本地文件与 Git 不会额外调用模型。查看本地交接草稿需要用户明确点击。

- [V1.7 功能、真实证据边界、兼容性和验收](docs/EXECUTION_ATLAS_V17.md)
- [V1.3–V2.0 路线图](docs/ROADMAP.md) · [每次修改的记录与下一步](docs/routine/)
- **不能把阶段和 CLI 启动画成已发生的远程模型请求**：只有官方结构化日志导入后才显示相应 Token；没有数据就显示“未知”。Git 结构变化是两次快照的观察结果，不能直接证明文件作者。
- 旧版任务只有 Git 状态而没有 V1.7 的目录结构检查点时，保持“证据不足”；新阶段开始/完成后才可建立结构前后对比。
- 本项目发布的是 Windows 自包含 EXE + 相邻 `ui-dist/` 文件；Windows CI 和真实 Hyper-V GUI 测试是不同的验收门槛。

---

# AIWS V1.3–V1.6 — Worktree · Windows ConPTY · Execution Ledger · Multi-Agent DAG

**当前开发交付：** 本轮新增源码和测试，Windows CI 与 Hyper-V 实机 GUI 验收须分别进行，不能以本地逻辑测试替代 EXE 编译。 [完整实施说明](docs/IMPLEMENTATION_V13_V16.md) · [产品路线图](docs/ROADMAP.md) · [开发日志](docs/routine/)。

- **V1.3**：每个 Agent 阶段按需建立受控的独立 Git Worktree / 分支；检查点和代码树在实际执行目录采集。
- **V1.4**：通过 Windows ConPTY + xterm.js 实现工作台内 PowerShell；必须人工确认启动，终端内容不存档也不自动发送模型。
- **V1.5**：持久化元数据事件账本，区分已记录的本地操作与未知模型活动。
- **V1.6**：具依赖校验与并发隔离约束的多 Agent DAG、可视化编排及只传直接依赖结果的上下文。

**重要边界**：这些能力不会将 Claude/ChatGPT 订阅登录信息转换为第三方 API；外部 Claude Code / Codex 仍通过官方 CLI 在人工确认后启动，无法自动捕获其全部模型回复。不提供未经批准的 Agent Shell 权限。独立 Worktree 不等于 Windows 安全沙箱。

Windows 构建：在 Windows 11 + Node.js 22 + .NET 10 下运行 `scripts/Build-NativeDesktop.ps1`。发布 EXE 需要相邻 `ui-dist/` 文件夹。旧版 V1.2 JSON 自动保留原任务数据；在升级前请备份 `%LOCALAPPDATA%\WindowsAIWorkstation`。

---

# AIWS V1.2 — Project structure & Git evidence (Windows native desktop)

The AIWS-owned Windows `.exe` now connects **workflow stages** to a **local project file tree, Git status, staged/unstaged per-file Diff, and recorded commit paths**. Use **文件与 Git 变更** in the left sidebar. The evidence is collected locally **without sending any source to Claude/Codex or spending model tokens**. Stage-associated Git changes are observations, **not automatically proof that an Agent wrote a file**.

Build the standalone Windows EXE by running `scripts/Build-NativeDesktop.ps1` on Windows with .NET 10 and Node.js 22; distribute `WindowsAIWorkstation.exe` together with its `ui-dist/` directory. See [V1.2 project evidence spec](docs/PROJECT_EVIDENCE_V12.md) and [change routine](docs/routine/2026-11-20_1420-project-tree-git-stage-evidence.md). The existing Git-only tool console, workflow, approval and execution components remain intact.

**Windows CI verified (2026-11-20):** React build, WPF/.NET core tests and self-contained EXE publishing passed: [Native Windows Desktop EXE run 44688011400](https://github.com/Nimenta727/Windows-AI-Workstation/actions/runs/44688011400). Hyper-V guest GUI testing is **not** yet complete; see [verification routine](docs/routine/2026-11-20_1431-v12-native-ci-verified.md).

---

# AIWS V1.0 — source-level modular Windows workstation

**New default:** our own Windows EXE hosting an offline React workspace UI, backed by the AIWS .NET workflow/approval/trace core. **Not** T3/OpenClaw embedded application pages or upstream servers. See [modular recomposition design](docs/MODULAR_RECOMPOSITION_V1.md).

Run `scripts/Build-NativeDesktop.ps1` on a Windows 11 VM with .NET 10 SDK, Node.js 22, and WebView2 Runtime; the distribution consists of `WindowsAIWorkstation.exe` **and** `ui-dist/` assets. Frontend source lives in `desktop/AIWorkstation.Frontend`; adapted MIT T3 components are documented at `third_party/t3code/NOTICE.md`.

The host does not automatically send prompts or convert ChatGPT/Claude subscriptions into API keys. CLI execution requires local confirmation and inherits Windows user permissions.

---

# Windows AI Workstation · native desktop edition

**Native Windows EXE, not a localhost webpage.** A new Windows-first AI agent workbench for Hyper-V virtual machines, inspired by the quiet, warm white desktop experience of Claude without copying its assets or product design.

> **V0.8 integration status:** new embedded upstream shell requires Windows CI compilation and VM runtime validation. V0.7 core remains intact. Earlier **V0.7 status:** native WPF/.NET compiled and Windows CI [verified successfully](https://github.com/Nimenta727/Windows-AI-Workstation/actions/runs/44657658528), including core smoke tests and x64 single-file EXE publish. This is a prototype, not a finished or audited operating system agent.

## V0.9 — one-click original professional frontend

With the original T3 Code interface already embedded in the native EXE, the home screen now includes **启动并连接已安装的 T3 Code**. If a loopback service is responding, AIWS connects without starting a duplicate. Otherwise it starts the *separately installed, official* `t3 serve --host 127.0.0.1 --port <selected>` process and briefly probes for readiness before loading the original UI in WebView2. The T3 process remains owned by the official tool and does not stop when AIWS exits.

- **Still the real upstream UI:** no imitations, scraped login data, or copied assets. T3 has its own React/RPC/server runtime and must be installed separately.
- **Still Windows-native:** the AIWS application itself is WPF/.NET and is packaged as a self-contained Windows EXE; original upstream UI runs inside an embedded WebView2 window.
- **Only T3 receives one-click launching:** OpenClaw continues to require a separately configured Gateway and local address. AIWS does not start Gateway services or manage OpenClaw credentials.
- **Conservative security:** only the explicitly validated local HTTP root address can be auto-launched; existing loopback service is checked first. Login happens through the upstream-supported flow, and AIWS does not collect subscription secrets.

Instructions: install the [official T3 CLI](https://github.com/pingdotgg/t3code#install), confirm `t3 --help` in PowerShell, then open `WindowsAIWorkstation.exe` and choose **启动并连接已安装的 T3 Code**. If it fails, verify the port displayed by the official service and use **连接本机服务**.

The next architectural milestone is an independently tested **source-level fork / adapter**. We do not claim that hosting the upstream UI means its source code, data store, or routing engine has been merged into AIWS.

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

## V1.1 — Git review and Windows developer tools (source-level integration)

In the Windows EXE, select an existing task and choose **终端与 Diff** in the left sidebar. The panel reads Git status, summary, staged/unstaged diffs, history and branch from the task's trusted local folder. Git commands are predefined, read-only and never submitted to an AI model. The separate **终端** tab opens Windows PowerShell *only after native user confirmation*; this version does not claim to embed a full ConPTY terminal. **Windows 权限** reports tool availability and whether user approval is needed.

The adapted T3 Code table primitive is MIT attributed; OpenClaw Windows and Kandev remain architectural references, not embedded backends. See `docs/DEVELOPER_MODULES_V11.md` and the timestamped record under `docs/routine/` for actual code ownership and verification.
