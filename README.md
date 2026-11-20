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

[OS 工程与构建 / OS build](os/README.md) · [内核和隔离设计 / Kernel & isolation](docs/AIWS_OS_BLUEPRINT.md) · [变更记录 / Routine](docs/routine/2026-11-20_2130-aiws-os-guest-bootstrap.md)

**权限模型 / Privilege model:** AI 可以在可丢弃的客户机中获得完整管理员操作能力，但宿主机磁盘、虚拟化控制接口、共享设备与凭据不属于客户机权限域。root 并不能替代虚拟机管理器的隔离；首次构建与 Hyper-V/KVM 实机安全验证尚待完成。

---

**Status / 状态**：v1.9.0-preview.1 is a **preview**. Windows CI and release artifacts are tracked separately from real Hyper-V GUI and permission testing. The latter remains pending. This README describes supported behavior, not inaccessible provider internals.
