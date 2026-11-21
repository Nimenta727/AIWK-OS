# AIWK-OS · AI Workstation & AI-native Linux guest

**中文** · [English](#english) · [文档中心](docs/README.md) · [代码结构](docs/CODEBASE_MAP.md) · [Git 开发记录](docs/routine/README.md)

> **工程预览 / Engineering preview** — 仓库包含两个不同的运行目标：Windows 原生 AI 工作台和实验性 AI 原生 Linux 客户机系统。不是已经正式发行的稳定操作系统。

## 项目定位

**AIWK-OS** 将可审计的 Agent 任务、计划、DAG、权限审批和执行证据组织成统一工作台。当前同时维护：

| 运行目标 | 技术实现 | 当前边界 |
| --- | --- | --- |
| **Windows 工作台** | WPF / .NET 10 + WebView2 + 共用 React 前端 | 有构建和自动化测试；实际 Hyper-V GUI、ACL、安装器与签名需另行验收 |
| **Linux AIWS OS** | Debian 13 Live ISO、Openbox/XFCE Shell、Chromium 应用窗口、systemd 用户服务、SQLite DAG | 实验系统；原生 BIOS/UEFI ISO 引导和实体硬件仍需独立验证 |
| **可选本地小模型** | llama.cpp / Qwen3.5-2B GGUF、只读建议与离线评测 | 权重与推理效果不由源代码存在自动证明；以真实 guest CI 结果为准 |

Windows 和 Linux 共用 `desktop/AIWorkstation.Frontend` 的 React 组件，但**不共用相同的操作系统权限**。Windows 任务历史可以受限导入 Linux 作证据，原有审批不能自动转化为 Linux 可执行权限。

## 当前实现与安全边界

Linux 客户机路径：**AIWS Shell → Workbench → 独立 systemd Agent → 同 UID Permission Broker → 持久化 DAG/工具 → 审计证据**。Broker 通过 UNIX Socket 核对运行中的阶段、参数与审批记录；MCP 对外只暴露只读入口。**这是应用层 fail-closed 策略，不是内核强制隔离**：相同 UID 的恶意进程及客户机 root 仍可能绕过。

BIOS/UEFI 原生 ISO 启动 CI 已加入，和原有 QEMU 直接加载内核的诊断路径分开。只有对应固件 CI 完成且通过，才能称为该固件路径验收通过；也不代表物理机器启动、安装升级或 Secure Boot 已通过。

## 快速开始

### Windows 11 x64 工作台

从 [Releases](https://github.com/Nimenta727/AIWK-OS/releases) 获取与版本匹配的**预发布** ZIP，完整解压，保留 EXE 相邻的 `ui-dist/`。需要 WebView2 Runtime。预览版可能未签名；请先核对来源及校验和，建议在非管理员测试环境运行。

开发者需要 Node.js 22、.NET 10 SDK 和 Windows PowerShell：

```powershell
.\scripts\Build-NativeDesktop.ps1
```

Windows CI 产物：[Native Desktop](https://github.com/Nimenta727/AIWK-OS/actions/workflows/native-desktop.yml)。

### Linux 客户机实验镜像

在隔离的 Debian 13 (trixie) 构建环境执行（需要 live-build/chroot 权限及软件包下载）：

```bash
sudo apt-get update
sudo apt-get install -y live-build debootstrap xorriso squashfs-tools
sudo ./os/debian/build.sh
```

生成镜像通常位于 `out/aiws-os/live-image-amd64.hybrid.iso`。在具备 KVM 的 Linux 宿主上可使用：

```bash
./os/host/run-qemu-offline.sh out/aiws-os/live-image-amd64.hybrid.iso
```

默认无网络、无宿主目录共享、无宿主设备直通。具体构建前提和限制见 [OS 工程指南](os/README.md)。**不要把 ISO 直接写入重要磁盘**；本项目还没有经验证的通用安装器。

## Alpha 0.1 开发路线

当前已启动 [M1–M4 工程计划](docs/AIWS_OS_ALPHA_PLAN.md)：M1 只读安装预检（**未启用安装或磁盘写入**），M2 原生应用启动器、通知和可选 Fcitx5 输入支持。M3 强制隔离与 M4 自主 Agent 完整验收仍未完成。具体状态以 CI 和真实虚拟机验证为准。

## 开发入口

| 需要做什么 | 阅读 |
| --- | --- |
| 理解目录、依赖和模块职责 | [代码结构与模块边界](docs/CODEBASE_MAP.md) |
| 查看当前产品功能和限制 | [文档中心](docs/README.md) |
| 固件启动、Shell、权限隔离的验收标准 | [OS 生产级门槛](docs/AIWS_OS_PRODUCTION_GATES.md) |
| Broker 的权限决策与威胁模型 | [Permission Broker](docs/AIWS_PERMISSION_BROKER.md) |
| 模型训练、独立评测和质量门禁 | [模型微调规范](docs/AIWS_MODEL_FINETUNING_STANDARD.md) |
| Windows 历史到 Linux Agent 的映射 | [迁移映射](docs/AIWS_WINDOWS_TO_LINUX_AGENT_MAPPING.md) |
| 查看每次修改、验证和下一步 | [Routine 日志](docs/routine/README.md) |
| 历史版本与旧版技术设计 | [历史资料导航](docs/HISTORY.md) |

## 发行与许可

目前是**工程预览**，不是正式稳定 OS 发行。Windows 打包、Linux ISO、真实固件启动、离线模型性能和安全隔离是不同验收门槛，不得互相代替。

仓库自有代码的当前许可证以 [LICENSE](LICENSE) 为准，**目前为 MIT**；第三方组件遵循各自许可证和署名义务。未来改为 Apache-2.0 需要单独处理贡献者与第三方授权，不能通过修改 README 自动完成。

---

## English

**AIWK-OS** develops a Windows-native AI workstation alongside an experimental Debian-based AI-native Linux guest. Both share React UI sources, but the WPF/.NET runtime and Linux systemd/SQLite Agent runtime are distinct products and trust domains.

- **Windows:** WPF/.NET 10, WebView2, task plans, worktrees, evidence and approval. CI coverage is not equivalent to completed Hyper-V manual acceptance.
- **Linux:** Debian 13 Live image, Openbox/XFCE native taskbar, Chromium app window, durable task DAG, independent Agent and same-UID Permission Broker. The Broker is **not** mandatory kernel-enforced confinement.
- **Local model:** optional GGUF/llama.cpp integration and a held-out guest benchmark. Model accuracy, refusal rates, memory and latency must be verified by completed real-guest runs.
- **Boot:** BIOS and UEFI ISO firmware jobs are separate from direct-kernel QEMU diagnostics. A passing static test is not proof of firmware or physical hardware boot.
- **License:** repository `LICENSE` currently states MIT; upstream and system-package licenses remain separate.

For build instructions, module ownership, security boundaries, historical designs and release gates, start at [Documentation](docs/README.md), [Codebase map](docs/CODEBASE_MAP.md), [OS build](os/README.md), and [Routine](docs/routine/README.md).
