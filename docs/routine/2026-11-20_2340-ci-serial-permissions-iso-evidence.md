# 2026-11-20 23:40 — Fix CI QEMU serial permissions and retain smoke ISO evidence

## 中文
**问题证据：** 首次 image and boot CI run 44757305155 已实际完成 Debian Live ISO 构建及哈希验证，QEMU 在启动前因 root 容器创建的 out 目录无法由 runner 写入 boot-serial.log 而退出 (Permission denied)。这不是客体系统启动故障。
**改动：** 将 QEMU 串口输出改到 runner 可写的仓库根目录 boot-serial.log，调整证据收集路径；无论 VM 启动通过与否都尝试上传短期实验 ISO，以免下次丢失镜像排查证据。
**涉及文件：** .github/workflows/aiws-os-image-boot.yml 和本 routine。
**验证：** 由真实 CI log 的 QEMU 权限失败定位，需重新执行 image/boot workflow 后判断是否进入客户机及桌面/Agent 验收。
**剩余问题：** NixOS 只通过求值，未经真实构建；Debian 的 VM 启动、图形会话和 Agent 仍待验证；完整开发工具链的 full ISO 未构建。
**下一步：** 观察第二次 QEMU 串口，修复客体启动异常；验证 desktop/AIWS HTTP 和 MCP 所有关键检测；再做 full ISO、NixOS ISO 和视觉 GUI 验收。
## English
The first Debian smoke ISO was built and SHA-verified; QEMU could not create a serial logfile inside a Docker-root-owned directory. Move serial logs to the runner-owned checkout root and retain ISO artifacts even on boot failure. Recheck real guest boot.
