# Debian 13 live-build adapter

主镜像构建入口：`os/debian/build.sh`（Git 模式必须为 **100755**）。在隔离的 Debian 13 trixie 构建容器中以 root/chroot 权限执行；它不是通用安装器。

- `config/package-lists/`：桌面、开发工具和客户机运行依赖。
- `config/includes.chroot/`：客户机内安装的 systemd 用户服务、AIWS Shell、Openbox 配置和运行入口。
- `profiles/`：用于 CI/真实模型的镜像构建配置。
- `../kernel/ci/firmware-iso-boot.sh`：从 **ISO 自身**经 BIOS 或 OVMF UEFI 引导，不使用 `-kernel` 捷径。
- `.github/workflows/aiws-os-image-boot.yml`：Debian live-build、固件、GUI 和 DAG 的 CI。

Shell 是 Openbox + XFCE panel + Chromium 应用窗口；GUI 测试涵盖窗口焦点、UTF-8 剪贴板、浏览器操作和任务执行。**CI 工作流存在不代表测试已通过**，需按对应 SHA 查看运行结果和固件串口日志。

构建脚本和系统服务的路径是打包契约。重构前必须更新复制清单、可执行权限、静态验证和实际 QEMU 验收。

[OS 工程说明](../README.md) · [固件与桌面验收](../../docs/AIWS_OS_PRODUCTION_GATES.md)
