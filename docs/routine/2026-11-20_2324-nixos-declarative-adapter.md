# 2026-11-20 23:24 — NixOS declarative OS adapter added

## 中文
**本次修改：** 为 AIWS OS 新增 flake.nix 及 os/platforms/nixos/aiws.nix。NixOS 26.05 声明式配置独立 guest 账号、XFCE/LightDM、Chromium 工作台、普通用户 systemd 服务、已有 Python/MCP Agent 工具和开机探针；共用 desktop React 和 os/runtime。保留 Debian 兼容 adapter，但 OS 核心不再绑定 Debian。
**影响：** flake.nix, os/platforms/nixos/aiws.nix, os/platforms/nixos/README.md，本 routine。
**验证：** 待 Nix CI 做语法与构建验证，未声称生成或启动 NixOS ISO。
**限制：** flake.lock、npm lock 未固定，React dist 以 --impure 外部路径导入；自动登录仅用于无网络的一次性测试 VM。全量自主 Agent 和特权 Broker 未完成。
**下一步：** 真正运行 Debian/QEMU 镜像 smoke，验证 Nix flake eval/ISO；固定锁文件、共享 UI 包、强化权限和 VM 安全。
## English
Add NixOS 26.05 declarative guest image profile powered by the same Linux runtime and React UI; retain Debian as a compatible adapter. Build, boot, pinning and isolation validation remain pending.
