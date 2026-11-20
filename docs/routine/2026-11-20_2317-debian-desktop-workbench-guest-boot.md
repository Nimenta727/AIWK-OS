# 2026-11-20 23:17 — Debian Live adapter integrates GUI, service and common React UI

## 中文
**改动：** Debian 13 仍保留作为首个 ISO 启动测试 adapter，但核心运行时代码不依赖 Debian。live-build 现在将共同的 aiws_workbench.py、React dist、workbench wrapper 打包；LightDM 实验性离线 VM 自动登录默认 user、XFCE autostart 启动 systemd --user 工作台服务，打开 Chromium 应用窗口；新增 systemd oneshot 开机烟测，在串口发出明确的 PASS/FAIL，检测 LightDM、XFCE 会话、HTTP 健康、UI 包及 MCP 工具。
**改动文件：** os/debian/build.sh; os/debian/config/includes.chroot/usr/local/bin/aiws-workbench, aiws-open-workbench, aiws-boot-smoke; os/debian/config/includes.chroot/etc/systemd/user/aiws-workbench.service; os/debian/config/includes.chroot/etc/xdg/autostart/aiws-workbench.desktop; os/debian/config/includes.chroot/etc/lightdm/lightdm.conf.d/50-aiws-autologin.conf; os/debian/config/includes.chroot/etc/systemd/system/aiws-boot-smoke.service; os/debian/config/includes.chroot/etc/systemd/system/multi-user.target.wants/aiws-boot-smoke.service; 本 routine。
**验证：** Linux shell 语法和 OS 静态合同将在 GitHub CI 测试；真实 ISO 构建、QEMU 启动、工作台 UI 和窗口联动需后续自动化运行结果支持，不能预称成功。
**风险：** 仅在默认无 NIC 的一次性测试 VM 使用 LightDM 自动登录；不能用于共享用户/联网机器。localhost HTTP 不是多用户安全边界。guest root 无法隔离 host root。未接入自主 LLM。
**下一步：** 增加实际 CI ISO 构建及 QEMU TCG 串口 smoke；排查登录、服务启动、桌面资源；NixOS declarative adapter；系统任务和 LLM Agent 对接。
## English
Wire the shared Linux controller and React UI into the existing Debian live-image adapter with an experimental offline XFCE auto-login, user systemd service and strict serial boot receipt. Await real image/VM validation, do not use auto-login for production.
