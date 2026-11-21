# AIWS OS / AI 原生 Linux 客户机系统

**状态 / Status:** 实验性工程预览。不是已通过物理硬件、安装升级和强制隔离验收的稳定 OS。

[仓库入口](../README.md) · [代码结构](../docs/CODEBASE_MAP.md) · [固件与 Shell 验收](../docs/AIWS_OS_PRODUCTION_GATES.md) · [权限 Broker](../docs/AIWS_PERMISSION_BROKER.md)

## 当前架构

```text
Debian 13 Live ISO / NixOS experimental adapter
  └─ Openbox + XFCE panel + Chromium AIWS app
       └─ Workbench localhost HTTP
            └─ systemd user Agent / SQLite DAG
                 └─ independent same-UID Permission Broker
                      └─ approved guest tools / audit
Optional local model → structured proposal → reviewed DAG
```

Linux OS 使用与 Windows 桌面版共用的 React 源码，但不运行 Windows WPF/.NET 桌面宿主。模型建议不会自动成为工具执行许可。

**安全声明：** Broker 是独立的非 root 用户态策略进程，核对持久化 DAG、工具参数和审批；它与 Agent 仍是同 UID，**不是不可绕过的 Linux 内核强制访问控制**。客户机 root 不等于宿主 root；客户机不能自动获得宿主虚拟化控制 API、共享文件或宿主凭据。

## 目录职责

| 目录 | 内容 |
| --- | --- |
| [runtime](runtime/README.md) | Agent、Broker、MCP、DAG、模型建议、工具 |
| [debian](debian/README.md) | Debian 13 live-build、桌面会话、systemd 服务 |
| [model](model/README.md) | GGUF/llama.cpp、离线模型评测和 LoRA 配方 |
| `kernel/` | 内核目标配置、UEFI A/B 与固件启动脚本 |
| `platforms/nixos/` | NixOS 声明式实验配方 |
| `host/` | 离线、无宿主共享的 QEMU 启动脚本 |
| `verify/` | Python 静态和客户机行为测试 |

## 构建 Debian Live ISO

要求隔离的 Debian 13 trixie 构建环境、可访问 Debian 软件包仓库，以及构建时的 root/chroot 权限：

```bash
sudo apt-get update
sudo apt-get install -y live-build debootstrap xorriso squashfs-tools
sudo ./os/debian/build.sh
```

默认输出 `out/aiws-os/live-image-amd64.hybrid.iso` 和 SHA-256。构建脚本仅允许预期的构建目录，不应在个人工作目录里直接清理或覆盖已有数据。

在 Linux KVM 宿主机以普通用户启动实验性 Live 镜像：

```bash
./os/host/run-qemu-offline.sh out/aiws-os/live-image-amd64.hybrid.iso
```

默认不接入宿主目录、网络或设备直通。**此命令不安装操作系统，不应当作磁盘安装器使用。**

## 验证与证据

```bash
python3 -m unittest discover -s os/verify -p 'test_*.py'
bash -n os/debian/build.sh
bash -n os/kernel/ci/firmware-iso-boot.sh
```

CI 分为静态契约、Debian 镜像、QEMU 直接内核诊断、ISO BIOS/OVMF UEFI 固件启动、GUI/DAG 和可选真实 2B 模型评测。**静态通过不能替代固件或模型实测。** 请查看对应提交的 [Actions](https://github.com/Nimenta727/AIWK-OS/actions) 结论及附件。

## 当前未完成

物理机器固件/USB 启动、通用安装器、Secure Boot、完整中文输入法/跨应用剪贴板、内核强制隔离的独立低权限执行 Worker、自动更新与恢复、真实模型稳定质量验收。NixOS 是并行适配，不应视为已发布的第二套稳定镜像。

许可证以根目录 [LICENSE](../LICENSE) 为准（当前 MIT）。Debian/Linux/浏览器/语言工具链的发行许可与源码义务必须分别履行。

---

## English

AIWS OS is an experimental Linux guest project using Debian 13 Live as the primary image recipe and NixOS as an exploratory adapter. It includes an Openbox/XFCE desktop, shared React workbench, independent systemd user Agent, SQLite task DAG and same-UID Permission Broker. The Broker is an **application-level decision process**, not mandatory OS isolation. Build/CI coverage does not certify physical boot, secure installation, model quality or production release. See the linked module READMEs and production gates for precise boundaries.
