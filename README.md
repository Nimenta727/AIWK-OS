# Windows AI Workstation · AIWS

**中文 / [English](#english)** · **v1.9.0-preview.1 · Engineering Preview / 工程预览版**

> 一个任务，多个可替换的 Agent。对话、计划、执行、Git、目录结构及证据由同一套本地任务控制层管理。
>
> One durable task, multiple interchangeable agents. AIWS correlates plans, workflows, source changes and execution evidence in a Windows-native workbench.

**[下载安装 / Download & install](#安装--installation)** · **[开发文档 / Documentation](docs/README.md)** · **[历史记录 / Historical logs](docs/routine/README.md)** · **[发行说明 / Release notes](docs/RELEASE_NOTES_V19.md)**

---

## 中文

### 这是一个什么产品？

AIWS 是自己的 **WPF / .NET 10 Windows 桌面 EXE**，通过 WebView2 承载离线 React 工作区界面，利用本地 .NET 核心管理任务与权限。它不是在窗口内嵌入完整的 T3 Code / OpenClaw，也不会把 Claude / ChatGPT 订阅凭据当成通用 API。

### 已实现的核心能力

| 模块 | 功能 | 必须知道的限制 |
| --- | --- | --- |
| 多 Agent 任务中心 | 统一任务目标、计划版本、工件、DAG 阶段、执行器能力、审批和调度票据 | 官方交互式 CLI 启动仍需用户确认 |
| **内部执行透视** | 可展开任务阶段、五段执行证据链、上下文清单、Token 证据、目录变化和文件 Diff | 没有官方可观测事件时真实模型调用与 Token 为未知 |
| 执行全景 / Git | Git Worktree、前后结构检查点、按文件的 Git Diff、已提交 HEAD 差异 | 阶段期间观察到修改并不严格证明 Agent 作者 |
| AI 计划中心 | Markdown 计划大纲、任务看板、状态与本地增量检测 | CLI 未保存到文件的规划不可被自动观察 |
| 上下文与 Token | 有来源的 HandoffBundle、本地字符估算与重复启动预算检查 | 不限制 CLI 内部所有模型请求或真实账单 |
| Windows 开发环境 | ConPTY 内置 PowerShell、原生 CLI 启动、Git 只读控制台、诊断 | Windows Worktree 不是 OS 沙箱；未完成 Hyper-V 实机安全验收 |
| 视觉与交互 | AIWS Studio 桌面布局、重复提交/过期请求防护、主导航中英文切换 | 新透视页可双语切换；部分旧专业面板仍是中文 |

### AIWS OS / 独立 AI 原生 Linux 系统（开发中）

项目现在同时包含 Windows WPF 兼容工作台和独立 Linux 客户机操作系统工程。Linux 版复用同一份 React 工作台源码，接入普通用户权限的本地 Agent 工具队列、代码智能引擎、图形桌面和系统服务；不依赖 Windows EXE。

- 系统底座不固定 Debian：Debian live-build 仍是第一套开机验证配方，新增 NixOS 26.05 声明式 ISO 配方。后续可为 mkosi、Fedora bootc 等开发独立 adapter。
- 已提交 Linux 工作台服务、MCP 工具接口、C#/Swift 代码分析和 React OS 页面；现有 Windows 工作台保留原有运行路径。
- **已实测：** Debian 实验 ISO 真正构建并 SHA 校验；[QEMU 直接内核启动与 LightDM/XFCE/guest HTTP/MCP](https://github.com/Nimenta727/Windows-AI-Workstation/actions/runs/44762589191) 全部通过。尚未完成原生固件 ISO 启动、工作台 GUI 实际可见与点击、NixOS ISO build/boot、自主 Agent、统一任务 DAG 迁移、权限 Broker 和宿主隔离安全验收。

**AIWS Shell 方向：** 已提交专用的 AIWS 主界面会话配方，客户机默认以 kiosk 工作台代替 XFCE 面板；已在 [真实 Debian/QEMU 验收](https://github.com/Nimenta727/Windows-AI-Workstation/actions/runs/44787989404) 中确认可见 Chromium 窗口、文件点击、DAG 创建/执行及 AIWS 主界面 framebuffer。已增加客户机持久 SQLite DAG、审批与审计以及可选离线小模型 JSON 建议层。真实模型权重与微调结果仍未交付，不能宣称内置 2B 已运行。

工程说明：[AIWS OS 模块化重构](docs/AIWS_MODULAR_OS.md)、[OS 工程](os/README.md)、[镜像与 QEMU 启动验证](https://github.com/Nimenta727/Windows-AI-Workstation/actions/workflows/aiws-os-image-boot.yml)。

**2026-11-21 Linux Agent 进展说明：** 已加入 Windows 计划修订/WorkItem/AgentRun/执行事件的受界只读迁移投影；旧阶段始终 UNMAPPED、不可执行。内置模型新增明确拒绝（refuse）协议、26 例独立中英双语评测集，以及真实 QEMU 的工具准确率、拒绝率、RSS、p50/p95 延迟采样链路。**本次代码提交并不代表 2B 模型已通过真实 QEMU 评测。** [模型微调规范](docs/AIWS_MODEL_FINETUNING_STANDARD.md) · [Windows→Linux 映射](docs/AIWS_WINDOWS_TO_LINUX_AGENT_MAPPING.md)。

### 安装 / Installation

1. 打开 [GitHub Releases](https://github.com/Nimenta727/Windows-AI-Workstation/releases)，选择最新的 **预发布版** ZIP。若预发布流程尚未完成，请使用 [Windows Actions 构建产物](https://github.com/Nimenta727/Windows-AI-Workstation/actions/workflows/native-desktop.yml)。
2. 在 Windows 11 x64（建议非管理员、隔离的 Hyper-V 虚拟机）中解压**整个 ZIP**，保留 `WindowsAIWorkstation.exe` 同目录的 `ui-dist/`。
3. 确认 WebView2 Runtime 已安装。若需使用 Agent，请自行安装并登录官方 Claude Code / Codex CLI；AIWS 不分发其二进制或账号凭据。
4. 运行 `WindowsAIWorkstation.exe`。创建任务，选择受信任的项目文件夹，再到「AI 协作总控台」「内部执行透视」「计划中心」查看执行证据。
5. 首次使用先备份 `%LOCALAPPDATA%\WindowsAIWorkstation`。发布包未签名；Windows 安全提示需自行核查来源与 SHA-256，不建议关闭系统防护。

**不要只复制单独 EXE**：离线前端静态资源也是发行物的一部分。

### 开发与测试

Windows 环境准备：Node.js 22、.NET 10 SDK、WebView2 Runtime。项目根目录执行：

```powershell
.\scripts\Build-NativeDesktop.ps1
```

或按组件执行：

```powershell
cd desktop\AIWorkstation.Frontend
npm install
npm test
npm run build
npm run test:ui

cd ..\..
dotnet run --project desktop\AIWorkstation.Core.SmokeTests\AIWorkstation.Core.SmokeTests.csproj --configuration Release
dotnet build desktop\AIWorkstation.Desktop\AIWorkstation.Desktop.csproj --configuration Release
```

- 自动测试：前端 Node 投影逻辑、Playwright Edge 点击/导航、.NET 核心烟测、Python legacy 回归。
- **CI ≠ Hyper-V 验收**。真实窗口、中文输入法、文件选择器、ConPTY 生命周期和 Windows ACL 需要在用户虚拟机单独验收。
- 查看 [发布检查清单](docs/RELEASE_CHECKLIST.md)、[架构与实现](docs/README.md)、[开发例行记录](docs/routine/README.md)。

### 安全、许可证与数据可信度

- **最小权限**：本地文件或 Git 操作受限制；Git 发布、危险系统行为不能靠前端任意命令触发。
- **无自动模型开销**：展开计划、文件、调度图、上下文来源和 Git 变更不自动调用模型。
- **可证实证据优先**：本地 CLI 启动、用户导入的结构化日志和 Git 观察结果分别标记。真实用量缺失时保持“未知”。
- **供应商边界**：不获取、转发或再利用 Claude / ChatGPT 的隐私订阅凭据。
- 项目自有代码按 [MIT](LICENSE) 授权；从 T3 Code 适配的 MIT 组件保留 [第三方署名](third_party/t3code/NOTICE.md)。Kandev 的 AGPL 源码未直接混入 MIT 代码。
- 详情见 [SECURITY.md](docs/SECURITY.md) 和 [变更日志](docs/routine/README.md)。

---

## English

### What is AIWS?

**Windows AI Workstation** is an independently developed Windows-native **WPF/.NET 10 executable** hosting locally bundled React assets in WebView2. It provides one durable source of truth for tasks, plans, agent execution, project changes and approvals. It is **not** a hosted copy of the entire T3 Code/OpenClaw application and does not convert subscription login credentials into third-party API access.

### Features and evidence limits

| Capability | What works | Important boundary |
| --- | --- | --- |
| Unified task control | Goals, acceptance criteria, plan revisions, artifacts, DAG stages, adapter capabilities and dispatch queue | Official interactive CLI launches remain explicitly user-confirmed |
| **Internal Observatory** | Task/agent topology, five-phase execution evidence, context manifests, token sources, changed directories and file diffs | Internal provider requests without structured evidence remain unknown |
| Git and structure | Per-stage worktrees, checkpoint comparisons, Git diffs and committed HEAD comparisons | Observed temporal changes are not proof of AI authorship |
| Plan Studio | Markdown outlines, Kanban, checklist progress and local refresh | Unwritten private provider plans are not observable |
| Context and token budgeting | Provenance-aware handoffs, estimated local budget warnings and duplicate-launch safeguards | Not a hard cap on provider-side usage or billing |
| Windows tools | ConPTY terminal, Git read-only console and official CLI integration | Not an OS sandbox; Hyper-V ACL and terminal acceptance are pending |
| UI and accessibility | Studio visual system and browser interaction tests | Primary shell and new observatory support Chinese/English; older specialist screens remain partly Chinese |

### AIWS OS (experimental modular Linux guest)

The repository now contains both the existing Windows WPF workstation and an independent Linux guest OS project. The Linux mode shares the SAME React source tree, backed by an unprivileged guest-local tool controller, MCP and code intelligence. Debian Live is the first boot-test adapter, while NixOS provides a declarative ISO adapter. Actual image/VM acceptance and autonomous Agent/privilege-broker integration are separate, incomplete milestones. See [modular OS design](docs/AIWS_MODULAR_OS.md).

### Install / Build

Download the latest **prerelease** ZIP from [GitHub Releases](https://github.com/Nimenta727/Windows-AI-Workstation/releases) or the [native CI artifacts](https://github.com/Nimenta727/Windows-AI-Workstation/actions/workflows/native-desktop.yml). Extract the entire ZIP on Windows 11 x64: the EXE **requires its adjacent `ui-dist/`**. Use a non-admin VM, confirm WebView2 availability, and install/authenticate official Claude Code or Codex CLI yourself if you intend to execute them.

From a Windows developer shell with Node.js 22 and .NET 10 SDK, run `./scripts/Build-NativeDesktop.ps1` from the repository root. The same project supports `npm test`, `npm run build`, `npm run test:ui` and .NET smoke tests as described above.

Back up `%LOCALAPPDATA%\WindowsAIWorkstation` before upgrading. **The preview executable is unsigned.** Validate its source and checksum. CI compilation, browser-level smoke coverage and Hyper-V native GUI/security acceptance are distinct gates.

### Architecture, privacy and license

AIWS keeps prompts, task records and project files local unless the user explicitly runs an authorized provider tool. Reading and visualizing local planning/Git evidence does not trigger model requests. Unknown provider token usage remains unknown rather than becoming a measured zero. Worktrees do not provide OS-level isolation. MIT applies to the AIWS-owned code; adapted upstream MIT primitives are attributed under `third_party/`. No AGPL Kandev source is incorporated.

Read the [documentation index](docs/README.md), [security guide](docs/SECURITY.md), [versioned release notes](docs/RELEASE_NOTES_V19.md), and [dated bilingual archival log index](docs/routine/README.md).


## AIWS OS · 独立 AI 虚拟机操作系统 / Standalone AI guest OS (early bootstrap)

> **区别于 Windows 桌面应用：** `os/` 是新建的 Debian 13 Live ISO 构建工程，不是 Windows WPF 的换皮版本。当前已提交镜像构建配置、预装图形开发工具、客户机内核/安全基线、离线优先的 KVM 启动脚本及静态验证；**尚未发布已验证可启动的 ISO，也尚未将原 WPF Agent 核心移植为 Linux 守护进程。**
>
> **Distinct product:** `os/` bootstraps a standalone Debian-based AI guest OS. It does not claim a tested boot image, a patched kernel, or a Linux port of the existing .NET/WPF agent host.

[跨平台代码智能 / Code intelligence](docs/AIWS_CODE_INTELLIGENCE.md) · [Windows/macOS 源码编写 / Cross-platform authoring](docs/AIWS_CROSS_PLATFORM_AUTHORING.md) · [AI 原生工具层 / Agent tool fabric](docs/AIWS_AGENT_TOOL_FABRIC.md) · [OS 工程与构建 / OS build](os/README.md) · [内核和隔离设计 / Kernel & isolation](docs/AIWS_OS_BLUEPRINT.md) · [变更记录 / Routine](docs/routine/2026-11-20_2130-aiws-os-guest-bootstrap.md)

**权限模型 / Privilege model:** AI 可以在可丢弃的客户机中获得完整管理员操作能力，但宿主机磁盘、虚拟化控制接口、共享设备与凭据不属于客户机权限域。root 并不能替代虚拟机管理器的隔离；首次构建与 Hyper-V/KVM 实机安全验证尚待完成。

---

**Status / 状态**：v1.9.0-preview.1 is a **preview**. Windows CI and release artifacts are tracked separately from real Hyper-V GUI and permission testing. The latter remains pending. This README describes supported behavior, not inaccessible provider internals.


### AIWS OS guest control plane / 客户机统一系统控制

已提交 guest-local SQLite DAG 任务与审核/重启恢复、AIWS systemd 用户服务固定白名单、内核版本化候选/哈希验证/撤销及恢复预案、本地 Qwen 2B 的可选 llama.cpp 适配与 GGUF 权重 SHA-256 版本注册和回滚。工作台已经增加客户机系统服务与内核候选页面，并可将本地小模型的只读建议保存为未执行的持久任务。**当前并不包含/实际运行 Qwen 2B 权重，LoRA 未训练，真实内核 A/B 启动/回滚机制未完成。** 客户机真实界面基础 smoke 已通过，扩展到内核候选图形审批的新验收仍待当前 CI 实际运行完成。详情见 [AIWS 客户机控制架构](docs/AIWS_GUEST_AGENT_SYSTEM_KERNEL.md)。


AIWS OS 2026-11-21 integration: a separate guest systemd Agent now owns the durable DAG for file/code inspection, approved file edits, allowlisted services and staged kernel candidates. Experimental guest-admin-only EFI A/B version management and real QEMU firmware fault-injection acceptance are under test. Optional, license-reviewed and SHA-256-pinned Qwen3.5-2B weights can be bundled in a guest ISO, with a separate real-QEMU inference gate. Do not claim successful real kernel recovery or deployed guest AI weights until their jobs actually pass. See docs/AIWS_GUEST_AGENT_SYSTEM_KERNEL.md.
