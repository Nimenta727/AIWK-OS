# 2026-11-20 23:31 — Fix YAML syntax blocking image boot CI

## 中文
**变更：** GitHub 首次执行新 workflow 时因步骤名称包含未加引号的冒号而拒绝解析，报告 run 44757065793 failure。现把 QEMU 步骤名称改成无冒号的合法 YAML 标量。
**文件：** .github/workflows/aiws-os-image-boot.yml 和本 routine。
**验证：** 已根据工作流实际解析失败定位问题；修正后必须观察新 workflow 是否进入 Nix 求值与 ISO 构建，不假定后续阶段成功。
**限制：** 当前无真实 ISO 或 QEMU 启动通过证据；首次解析错误不是客体运行错误。
**下一步：** 收集真实构建/启动 logs；排查镜像依赖、systemd/LightDM/XFCE 和服务；Nix flake 问题单独修复。
## English
Fix the unquoted colon in a GitHub Actions step title that prevented the image boot workflow from being parsed. Monitor subsequent real build/boot jobs; no guest acceptance claimed yet.
