# AIWS OS — 模块化 AI 原生系统重构 / Modular OS

**状态：真实镜像与开机验收仍在进行中；请以 GitHub Actions 完整结果为准。**

## 工作台优先 / Workbench-first

AIWS OS 不是在某套 Linux 桌面上附加聊天应用。它以工作台为人机交互入口，以 Agent 工具层和系统服务为机器调用入口；React UI、系统健康、文件与代码能力、Agent 工具结果应有一条统一的任务与证据链。

共用的 frontend 来源为 desktop/AIWorkstation.Frontend。Windows 版仍使用 WPF/WebView2；Linux 版由单用户、普通权限的本地 HTTP 服务显式切换 UI 模式。客户端不直接运行任意 shell；客户机本地只读任务队列提供工具列表、任务 ID、状态、结果和可审计元数据。

Linux 共享运行时位于 os/runtime，包括 aiws_workbench.py（本地任务控制器）、aiws_toolplane.py 与 aiws_mcp.py（工具接口）、aiws_codeintel.py（C#/Swift 静态候选索引）和 aiws_crossplatform.py（Windows/macOS 源码工程）。这几项不依赖 Debian 包管理器。

## 框架选择 / OS frameworks

| 框架 | 优势与定位 | 当前决策 |
| --- | --- | --- |
| NixOS | 声明式系统模块、软件包、桌面、systemd 和 ISO 构建 | 主要深度定制目标，已添加 experimental flake |
| systemd mkosi | 可针对多个 Linux 发行版构建 OS 镜像 | 后续多发行版通用镜像适配器 |
| Fedora bootc | 镜像化部署、原子更新与回滚方向 | OTA 和稳定发行阶段再评估 |
| Yocto/OpenEmbedded | 自定义 Linux 的构建层与元数据 | 未来底层或专用设备方向 |
| Buildroot | 最小 Linux 根文件系统与交叉编译 | 不优先作为完整 Chromium/IDE 桌面底座 |
| Debian live-build | 现成 XFCE/开发软件包，易于第一轮 GUI 与 Agent 启动测试 | 保留首个真实开机 adapter，不再绑定 OS 核心 |

参考：[NixOS 官方手册](https://nixos.org/manual/nixos/stable/)、[Nix ISO 构建](https://nix.dev/tutorials/nixos/building-bootable-iso-image.html)、[systemd mkosi](https://github.com/systemd/mkosi)、[Fedora image mode](https://fedoraproject.org/wiki/Initiatives/Image_Mode%2C_Phase_2_%282026%29)、[Yocto](https://www.yoctoproject.org/development/technical-overview/)、[Buildroot](https://buildroot.org/downloads/manual/manual.html)。

## 模块边界 / Directory layout

1. desktop/AIWorkstation.Frontend — 唯一共享 React 前端；Windows 与 Linux 只切换宿主接口。
2. os/runtime — Linux distro-neutral Agent/MCP、代码引擎与工作台 HTTP 入口。
3. os/debian — 第一套 Debian 13 Live ISO adapter；包括 XFCE 自动登录实验配置、user systemd 服务与开机诊断。
4. os/platforms/nixos + flake.nix — NixOS 26.05 声明式系统 adapter，复用同一 React 构建产物和 Python 运行时。
5. os/verify — 离线回归与 HTTP API 集成测试，不代替真实 VM 测试。
6. os/host — 不以宿主 root 启动、默认无 NIC/无共享目录的 QEMU 实验启动器。
7. .github/workflows/aiws-os-image-boot.yml — 真正构建 Debian smoke ISO，检查哈希、QEMU TCG 开机串口；另验证 NixOS 配方可解析与求值。

## 验收证据 / Acceptance gates

- 单元测试仅能证明代码行为与静态安全契约，不等于 OS 已启动。
- NixOS 配方 parse/eval 通过不等于 NixOS ISO 已构建或系统已启动。
- Debian smoke image 省略部分大型语言编译器，但仍包含 XFCE、LightDM、Chromium、Python Agent 和共享 React UI，目的是快速验证系统服务贯通。
- 真正开机验收要求 QEMU guest 经 LightDM、XFCE、HTTP health、React UI 和 MCP 检查后在 ttyS0 输出 AIWS_BOOT_SMOKE_PASS；失败则必须明确报错。
- QEMU TCG 进程级检查不代表真实 UI 点击、音视频、IME 或 Hyper-V/KVM 安全验收。
- 两个 adapter 的实验镜像启用自动登录，仅可用于无网络一次性 VM；不可直接用于共享/联网环境。

## 尚未完成

Nix flake.lock 与 npm lockfile 尚未固定；NixOS UI 构建目前需要显式传入 AIWS_UI_DIST 和 --impure，并非完全可重复构建。Windows 工作台完整任务数据库/DAG/审批模型还没有迁移到 Linux Agent。自主模型服务、guest root Broker、持久化 VM 磁盘、系统升级/回滚、GPL/Apache/MIT 许可证与 SBOM、端到端安全隔离，都仍须实装和实测。

## 下一步

先获得实际 ISO 构建及 QEMU 启动证据，并纠正任何真实故障。之后以工作台作为唯一任务入口，把 Windows 现有统一任务状态、计划、执行记录、Agent 适配器和审计迁入 Linux controller，再做跨发行版升级、受控权限操作、完整 GUI 自动化与宿主隔离测试。

## English

AIWS OS is a modular, workbench-first Linux guest architecture. The same React source serves Windows and Linux hosts. Distro-neutral guest tool services are separate from Debian Live and NixOS image adapters. Actual boot and safety claims require evidence; Windows task orchestration and autonomous LLM control are not yet ported.
