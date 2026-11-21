# AIWK-OS · 面向程序员的 AI 原生操作系统

**中文** · [English](#english) · [文档中心](docs/README.md) · [代码结构](docs/CODEBASE_MAP.md) · [开发记录](docs/routine/README.md)

> **一句话定位：你用自然语言说要做什么，系统替你去操作；你只需要「看」和「批准」。**
> AIWK-OS 是一个专为程序员设计的 Debian 系 Linux 发行版。它的首页不是桌面，而是一个**只读的观察台**——
> 展示 token 用量、模型状态、调用状态、任务进度和审计结论；需要手动开发时，再打开内置的 **AIWS Code** 编辑器和完整的语言工具链。

> **工程预览 / Engineering preview** — 这是处于开发中的实验系统，**不是**稳定发行版。哪些部分已经验证、哪些没有，见下方[「现在到了哪一步」](#现在到了哪一步)。

## 它是什么，不是什么

| 它是 | 它不是 |
| --- | --- |
| **自然语言驱动**的开发环境：说需求，系统拆任务、走审批、交给模型和工具去做 | 又一个需要你逐项点击的传统桌面 |
| **本地小模型当中转站**：离线运行，只负责理解指令、做本机文件/系统基础操作，并把大任务转交给云端 | 一个联网、能自己下载、自己执行任何命令的“全能 Agent” |
| **云端大模型通过官方 CLI**（Claude Code / Codex）接入，在你一次性授权的范围内工作；不存放 API 密钥 | 绕过厂商认证或保存你账号凭据的工具 |
| **一切可审计**：每次调用、每个阶段、每次审批都有记录，首页给出一句话结论 | 黑盒：你看不到模型做了什么 |
| 面向程序员：**常用语言环境与开源工具预装**，AIWS Code（Code - OSS 重新品牌化构建）随需打开 | 面向普通办公用户的系统 |
| **省 token、省资源**：本地模型空闲即卸载，用量只统计提供方上报的真实数字 | 不计成本地把所有事都丢给云端 |

## 工作方式

```text
你（自然语言）
   │
   ▼
┌──────────────── 观察台（首页，只读） ────────────────┐
│ token · 模型状态 · 调用状态 · 任务 · 审计结论 · 待你批准  │
└───────────────────────────────────────────────┘
   │ 指令                                   ▲ 事件与证据
   ▼                                         │
本地小模型（离线中转）──只提议，不执行──▶ 审批 DAG ──▶ 本机文件/系统工具（受限、可撤销）
   │ 超出本地能力，且你已授权
   ▼
官方 CLI（Claude Code / Codex）──专用低权限用户 + 出口域名白名单──▶ 在授权目录里构建项目
```

三条不变的原则：

1. **模型只提议，执行要审批。** 写操作永远生成「待批准」阶段；删除只是移到可恢复的回收站。
2. **本地模型不联网。** 它只能读取下载进度、系统和网络**状态**，不能下载、不能抓取。
3. **云端构建有边界。** 一次授权 = 一个目录 + token 预算 + 工具清单 + 时长上限；以独立低权限用户运行，网络只允许访问白名单域名（内核防火墙 + 代理双重限制）。

## 程序员开箱即用

- **语言与运行时**：Python（含 pip/venv/pipx）、Node.js + TypeScript、Go、Rust、Java（OpenJDK 21 + Maven）、Ruby、PHP、Lua、C/C++（gcc/g++/clang/clangd/cmake/meson/ninja）；清单见 `os/debian/config/package-lists/`，包名已对照真实 Debian 索引校验。
- **常用开源工具**：git / gh / git-delta、ripgrep / fd / jq、tmux / neovim、gdb / valgrind、shellcheck / shfmt、SQLite / PostgreSQL 客户端、编程字体等。
- **AIWS Code**：基于 [Code - OSS](https://github.com/microsoft/vscode)（MIT）源码的重新品牌化构建，保留上游版权与第三方声明，**不使用** Microsoft 的名称、图标、市场和服务；扩展来自 Open VSX。见 [os/ide/NOTICE.md](os/ide/NOTICE.md)。
- **一切围绕工作台**：「工具」侧栏集中列出内置与外部工具——文档阅读器（Markdown / CSV / JSON / 图片 / PDF / DOCX / 沙箱 HTML）、内置预览浏览器（本机开发服务与工作区页面）、终端、Chromium、文件管理器、AIWS Code，以及 git / gh / rg / jq / sqlite / pandoc 等命令行工具。读取类工具（`tools.list`、`doc.text` 等）AI 可通过受审计的工具接口自动调用；桌面程序只在你点击时启动。
- **工作台界面参照 VS Code 布局**：活动栏、侧边栏（真实文件树）、标签页、底部面板、状态栏、命令面板（`Ctrl+Shift+P`），深色/浅色主题。观察台是第一个、固定的标签页。

> 有意没有包含的：.NET SDK、pnpm、black、ruff 不在 Debian 主仓库（可用 pipx/npm 自行安装）；Docker 因权限模型另行评估。说明见 [软件包清单](os/debian/config/package-lists/aiws-devtools.list.chroot) 开头的注释。

## 现在到了哪一步

| 部分 | 状态 |
| --- | --- |
| 观察台、审批 DAG、本地模型接口、路由、官方 CLI 监督器、出口代理、AIWS Code 启动接口 | **代码已实现，单元/契约测试通过**（Python 438 项、前端 70 项） |
| 前端（VS Code 风格外壳） | **已在真实浏览器里点过**（深/浅主题、标签、命令面板、文件查看） |
| Debian 13 完整镜像（含工具链、AIWS Code、模型权重） | ✅ [v0.2.0-preview.1 测试版](https://github.com/Nimenta727/AIWK-OS/releases/tag/v0.2.0-preview.1)：构建通过、从 ISO 读回校验模型权重、QEMU 启动冒烟（含界面点击）通过 |
| AIWS Code 的真实构建 | ✅ 构建成功并打进镜像（许可文件已校验）；在镜像里的完整可用性**待验证** |
| 真实客户机里的模型质量、官方 CLI 实跑、完整镜像体积 | **未验证**（有检查清单，等待真实运行） |
| 内核强制隔离、通用安装器、Secure Boot、物理机启动 | **未完成**；当前 Permission Broker 是应用层策略，不是内核隔离 |

静态测试通过**不等于**固件、真机、模型或发行验收通过。

## 快速开始

### 试用测试版 ISO（推荐在虚拟机里）

1. 到 [Releases](https://github.com/Nimenta727/AIWK-OS/releases) 下载标有 **Pre-release** 的 `aiws-os-*-amd64.iso`（如被拆成 `.01 .02 …` 分卷，按 `REASSEMBLE.txt` 用 `cat` 合并），并用 `SHA256SUMS` 校验。
2. 在 QEMU / VirtualBox / VMware 里新建一台 **x86-64、≥6 GB 内存、≥2 核** 的虚拟机，把 ISO 当光盘启动；**不要写入重要磁盘**（没有经验证的安装器）。
   QEMU 示例（离线、无宿主共享）：`./os/host/run-qemu-offline.sh aiws-os-*.iso`
3. 自动以用户 `user` 登录（Live 默认密码 `live`），桌面上会打开工作台：首页是观察台；`Ctrl+Shift+P` 打开命令面板。
4. 想用本地模型：在「本地 AI 助手」页点“申请启用模型”（默认关闭）；想用云端：先在终端里用官方 CLI 登录（本系统不保存密钥），再在观察台里授权一次构建。

**该测试版需要你帮忙验证的**见 [发行说明](docs/RELEASE_NOTES_OS_PREVIEW.md) 的“请你验证”清单。

### 自己构建镜像

在隔离的 Debian 13 (trixie) 构建环境（需要 root 与网络）：

```bash
sudo apt-get install -y live-build debootstrap xorriso squashfs-tools zstd
(cd workbench && npm install && npm run build)
sudo ./os/debian/build.sh            # AIWS_OS_PROFILE=smoke 为不含开发工具链的小镜像
```

可选：先按 [os/ide/README.md](os/ide/README.md) 构建 AIWS Code，用 `AIWS_CODE_TARBALL` / `AIWS_CODE_SHA256` 嵌入；嵌入模型权重见 `os/debian/build.sh` 里的 `AIWS_OS_BUNDLED_MODEL_GGUF` 一组变量。
官方发行镜像由工作流 [`release-preview.yml`](.github/workflows/release-preview.yml) 构建，只在构建、校验和、QEMU 启动冒烟全部通过后才发布 pre-release。

### 只看工作台界面（不需要整个系统）

```bash
cd workbench && npm install && npm test && npm run build
python3 os/runtime/aiws_workbench.py --help      # 客户机本地服务，仅监听 127.0.0.1
```

## 仓库地图

| 目录 | 内容 |
| --- | --- |
| `workbench/` | React 工作台前端（VS Code 风格外壳 + 观察台 + 阅读器 + 预览浏览器） |
| `os/runtime/` | 客户机 Python 服务：Workbench、Agent、Broker、任务 DAG、模型网关/路由、观察台、构建监督（模块清单 `MODULES`） |
| `os/debian/` | live-build 配方、软件包清单、systemd 单元、桌面 Shell |
| `os/ide/` | AIWS Code：构建配方、补丁、品牌资源、许可说明 |
| `os/builder/` | 官方 CLI 构建通道的隔离与自检 |
| `os/model/` | 本地模型运行器、数据集 v1–v3 生成与评测 |
| `os/verify/` | 静态契约与行为测试 |
| `docs/` | 当前文档；`docs/history/` 旧资料；`docs/routine/` 每次修改的记录 |

旧的 Windows 工作台、旧 Python 控制平面和 NixOS 配方已移入 Git 历史（见 [docs/history](docs/history/README.md)）。细节见 [代码结构](docs/CODEBASE_MAP.md)。

## 开发入口

| 需要做什么 | 阅读 |
| --- | --- |
| 理解系统路线与已定决策 | [AI 原生路线](docs/AIWS_NATIVE_AI_PLAN.md) · [观察台计划](docs/AIWS_OBSERVATORY_PLAN.md) · [模型路由](docs/AIWS_MODEL_ROUTER.md) |
| 安全边界与威胁模型 | [SECURITY](docs/SECURITY.md) · [Permission Broker](docs/AIWS_PERMISSION_BROKER.md) |
| 固件启动、Shell、隔离的验收标准 | [OS 生产级门槛](docs/AIWS_OS_PRODUCTION_GATES.md) |
| 发行流程与检查表 | [发行说明（OS 预览）](docs/RELEASE_NOTES_OS_PREVIEW.md) · [CHANGELOG](CHANGELOG.md) |
| 第三方组件与许可 | [第三方清单](docs/THIRD_PARTY.md) |
| 每次修改、验证与下一步 | [Routine 日志](docs/routine/README.md) |

## 许可

仓库自有代码遵循根目录 [LICENSE](LICENSE)（**Apache License 2.0**）。第三方组件（Debian 软件包、Code - OSS、llama.cpp、各语言工具链等）遵循各自许可证，见 [第三方清单](docs/THIRD_PARTY.md)；
重新品牌化不改变上游许可，也不去除上游署名。

---

## English

**AIWK-OS is an AI-native operating system designed for programmers.** You describe what you want in natural language; the system operates for you, and you mostly *watch and approve*.

- **Home screen = a read-only Observatory**: token usage, model status, call status, tasks, and a one-sentence audit verdict. Detailed logs and request payloads are one click away, only when you ask.
- **A local, offline small model is the relay.** It understands instructions and performs basic file/system operations, but it only *proposes*; every write needs your approval. It never touches the network.
- **Cloud models come through the official CLIs** (Claude Code / Codex) under a one-time *mandate* (directory, token budget, tool list, time limit), as a dedicated unprivileged user behind a kernel firewall and a domain-allowlist proxy. No API keys are stored.
- **Built for developers**: common language toolchains and open-source tools are preinstalled, and **AIWS Code** — a rebranded build of the MIT-licensed Code - OSS (no Microsoft names, logos, marketplace or services; upstream credits kept) — opens on demand. The workbench UI follows the VS Code layout (activity bar, side bar, tabs, panel, status bar, command palette; dark/light themes).
- **Token- and resource-frugal by design**: the local model unloads when idle, and usage numbers are only what the provider reports.

**Status: engineering preview.** Code and unit/contract tests exist (Python 438, frontend 70) and the UI was exercised in a real browser. The AIWS Code build, real-guest model quality, real CLI runs, image size, firmware/physical boot and kernel-enforced isolation are **not verified yet** — see the table above. The Permission Broker is an application-level policy, not OS-level confinement.

Repository code is licensed under Apache-2.0 (see `LICENSE`); third-party components keep their own licenses ([docs/THIRD_PARTY.md](docs/THIRD_PARTY.md)).
Start at [Documentation](docs/README.md), [Codebase map](docs/CODEBASE_MAP.md), [OS build](os/README.md) and [Routine log](docs/routine/README.md).
