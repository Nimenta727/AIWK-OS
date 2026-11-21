# AIWS OS — independent AI virtual-machine operating system / 独立 AI 虚拟机操作系统

**Stage / 阶段:** P0 build scaffold; NOT a tested or released operating system. The Windows WPF workstation remains a separate compatibility application.

## 中文

产品目标是可独立引导、深度定制的 **Linux Guest OS**。其桌面、浏览器、IDE、终端、Agent 编排、诊断与内核策略在系统镜像内组成统一环境，而不是在 Windows 桌面应用上再叠一个虚拟机 UI。

首批工程以 **Debian 13 (trixie) amd64 + live-build + XFCE4** 为可复现基础：
- `os/debian/build.sh`：使用 Debian live-build 从包仓库构建 ISO-hybrid Live 镜像。
- `os/debian/config/package-lists/`：Firefox ESR、Geany、终端、Git、Python、Node.js、Java、Rust、Go、C/C++、调试和构建工具，来自 Debian 分发包；不引入未经授权的闭源二进制。
- `os/debian/config/includes.chroot/etc/sysctl.d/`：客户机内核运行时安全/开发工具配置。客户机 root **可修改这些设置**，它们不是宿主机安全边界。
- `aiws-system-status`：在客户机终端查看内核/虚拟化识别、编译工具和环境状态；不会自动启动或伪装已存在的 Agent。
- `aiws-admin-session`：只能在客户机交互式终端确认后调用 sudo；提供完整客户机系统管理会话，无网页远程提权接口。
- `os/host/run-qemu-offline.sh`：Linux KVM 宿主机离线启动实验用 ISO；默认**无网络、无共享目录、无主机设备直通**，拒绝以宿主机 root 运行。
- `os/kernel/aiws-kernel.fragment`：未来专用内核包的目标选项，**还没有重编译或替换 Debian 内核**。
- `os/verify/test_config.py`：静态安全契约和配置回归；不代替启动测试或逃逸攻防验证。

### AI 原生工具 / AI-native tool interface

本轮追加 [AIWS Tool Fabric](../docs/AIWS_AGENT_TOOL_FABRIC.md)：构建时安装客户机本地实验性 MCP stdio 工具端点 aiws-toolctl，支持限定工作区的代码、文件、Git、测试和受限制的无头 Chromium DOM 快照。真正的 Linux Agent 控制器与特权 Broker 尚未完成。

### Windows/macOS 源码工程

[跨平台源码生成 / Cross-platform source authoring](../docs/AIWS_CROSS_PLATFORM_AUTHORING.md)：内置 MCP 的 platform.inspect/project.scaffold，可从 Linux 客户机识别/创建 Windows WPF、macOS SwiftUI 源码工程；不代表可以在 Linux 运行原生 Windows/macOS 应用。

### 跨平台代码智能 / Code intelligence

[只读索引与 MCP 接口](../docs/AIWS_CODE_INTELLIGENCE.md)：可查询 C#/Swift 定义候选、词法引用、MSBuild/SwiftPM 清单和 WPF/WinUI/SwiftUI API 线索；所有结果明确区分未经 Roslyn/SourceKit-LSP 验证的推断。

### 构建

在 **Debian 13 amd64** 构建机/CI 容器内（需真实网络获取 Debian 软件包和 root/chroot 权限）：

```bash
sudo apt-get update
sudo apt-get install -y live-build debootstrap xorriso squashfs-tools
sudo ./os/debian/build.sh
```

输出是 `out/aiws-os/live-image-amd64.hybrid.iso`（以及 `.sha256`）。构建目录必须是新目录；脚本不会清除已有构建/用户工作区。**目前没有声称执行过此构建。**

Linux KVM 宿主（普通账号拥有 /dev/kvm 访问权限）：

```bash
./os/host/run-qemu-offline.sh out/aiws-os/live-image-amd64.hybrid.iso
```

默认 ISO 只读，不接入现有宿主磁盘。断电将丢失 Live 会话更改。首次构建后应检查 UEFI/BIOS、声卡/显示/输入、中文 IME、内存、DNS、防火墙与隔离功能，收集完整记录。

### 权限和许可证

客户机可运行 root，但**不允许**把宿主 root、Hyper-V/KVM 管理 API、宿主文件夹或其他账户凭据交给客户机。浏览器永不获得宿主桥接权限。联网模式与可持久化虚拟磁盘需另行设计宿主侧访问控制及显式授权。不可把“已经配置客户机 sysctl”当成已隔离的证据。

本阶段仅组合 Debian 官方源软件包，**没有**在 Git 仓库复制 Linux 内核、Firefox、IDE 或语言运行时。未来分发生成的 ISO 时必须随发行物提供相关 GPL/LGPL/MPL/Apache/BSD/MIT 许可证与源码提供义务；仓库根目录当前仍为 MIT，用户要求迁移 Apache-2.0 的事项需逐文件/贡献者确认，不能擅自为第三方代码改授权。

## English

This is a **standalone, bootable AI guest operating system project**, not a WPF theme. Phase P0 provides a Debian 13 Live image recipe, GUI browser/IDE/developer tools, guest-only system configuration, an interactive guest administrator entrypoint, and offline-by-default KVM test launcher. The existing Windows WebView2 bridge and Agent host have **not** yet been ported to Linux; packaging a full AIWS session and a reviewed guest execution broker are subsequent milestones. The kernel fragment is a *design target*, not a compiled custom kernel.

Build with Debian 13 as above; validate with `python3 -m unittest discover -s os/verify`. See [kernel/isolation design](../docs/AIWS_OS_BLUEPRINT.md) and [routine log](../docs/routine/2026-11-20_2130-aiws-os-guest-bootstrap.md). Host-side security policy, VM escape testing, and actual ISO boot validation remain open requirements.


## 2026-11-21 experimental system-level progress

The earlier bootstrap description is retained for history. Current Debian guest defaults to a dedicated AIWS Shell and an independent systemd user aiws-agent.service over a same-UID private UNIX socket. File edits and kernel candidate mutations must use the same durable, reviewed DAG. An interactive guest-root-only A/B manager is packaged for guest EFI installations, but the standard Live ISO has no persistent EFI slot. Guest Qwen3.5-2B weights can optionally be included in a hash-pinned, licensed model-inclusive image. Normal smoke ISO remains model-free.

Both real firmware A/B recovery and actual in-guest Qwen 2B inference require CI acceptance, which has not been established by the code changes themselves.


## 2026-11-21 contributor gates / 当期微调及迁移验收入口

- [2B 微调与独立评测规范](../docs/AIWS_MODEL_FINETUNING_STANDARD.md)：中英 held-out 测试、明确拒绝率、guest RSS/时延、复现证据和 LoRA 回滚。实际 QEMU 模型评测必须通过 ci 后才可宣称完成。
- [Windows→Linux Agent 历史投影](../docs/AIWS_WINDOWS_TO_LINUX_AGENT_MAPPING.md)：计划修订、WorkItem、AgentRun 和执行事件仅作受界证据；导入阶段不可执行，不复用 Windows 审批。

## Firmware ISO and interactive Shell acceptance

The standard Debian smoke ISO now assembles Openbox + XFCE native panel,
a maximized normal Chromium application window rather than kiosk,
Super+Enter/ Super+E shortcuts, and X11 focus + UTF-8 clipboard probes.
The image CI adds **actual El Torito BIOS/OVMF UEFI ISO boot** jobs
(without -kernel/-initrd) while preserving the diagnostic direct-kernel
tests and separate ESP A/B fixture. Passing these CI tests is not proof
of physical boot, CJK IME completeness, installer, secure update, or
non-bypassable worker sandbox. See the
[OS production gates](../docs/AIWS_OS_PRODUCTION_GATES.md).
