# 2026-11-20 23:29 — Build and boot acceptance pipeline / 真实镜像与虚拟机启动流水线

## 中文
**改动：** 新增 GitHub Actions AIWS OS image and virtual-machine boot acceptance：首先构建与 Windows 共享的 React UI，Debian trixie 一次性 root 构建容器生成真实 ISO，计算 SHA-256 并验证；Ubuntu runner 使用 QEMU TCG（无 /dev/kvm）和 **-nic none** 启动，等待客体系统开机探针在 ttyS0 报告 LightDM、XFCE、loopback Agent、React UI、MCP 的合格凭据。仅对真正 PASS 的镜像上传短期测试 ISO，始终上传调试串口日志。另设置 NixOS profile parse/eval 作业，避免把未经验证的 Nix 配方称为有效。
**影响文件：** .github/workflows/aiws-os-image-boot.yml, os/debian/build.sh, os/debian/profiles/smoke.list.chroot, os/platforms/nixos/aiws.nix，本 routine。
**验证：** 该提交本身只创建可执行流水线；需要观察 GitHub Actions 的完整成功/失败、明确区分构建、VM 启动、桌面和 agent。Debian smoke profile 省略附加语言编译器，不等同完整开发环境 ISO。
**已知限制：** GitHub hosted runner 不提供 KVM：TCG 启动慢且不代表真实 KVM/Hyper-V 安全验收。是否能在免费 runner 存储/时间内完成 full ISO 不保证。自动登录只用于离线测试。NixOS 暂时仅求值，未运行其 ISO。
**下一步：** 观察实测工作流并排查依赖、镜像体积、LightDM/XFCE/Chromium/Agent 启动错误；NixOS 构建 ISO 与锁文件；补充真实浏览器窗口截图/交互和宿主安全试验。
## English
Add real Debian Live ISO build, SHA verification, QEMU TCG boot and strict serial evidence tests for desktop/workbench/MCP; add NixOS parse and eval CI. Smoke image trims optional toolchains. Actual CI outcome must be checked before claiming acceptance.
