# 2026-11-21 01:08 — Make P0/P1 gates visible in root and documentation

## 变更
- 将用户再次强调的四项主线（真实可交互的 GUI，Linux 任务/计划/DAG/Agent/审计统一控制层，NixOS 真正 ISO 构建与开机，guest-only 权限/资源/恢复）加入 docs 入口，并明确作为**不得被模型和内核新功能替代的验收门槛**。
- 把最新 guest-only 权限边界、挂载防护、工作台文件结构管理的最近 routine 记录补充到 docs/routine/README.md。
- 修正根 README 过时说法：真实 Debian 实验 ISO 已经构建，QEMU 直接内核启动的 XFCE/HTTP/MCP 已通过；不将其混同为原生 ISO 固件启动或工作台界面点击验收完成。
- 变动：README.md，docs/README.md，docs/routine/README.md，本 routine。

## 验证与后续
依据成功的 run 44762589191 与当前 recent CI。尚未完成四项完整验收。下一步必须以 P0 GUI 点击测试为先，再做 Linux 持久 DAG 与任务恢复，NixOS ISO build/boot，客户机权限 Broker。任何 Agent 核心代码或 kernel 补丁不得涉及宿主机文件、命令、内核、共享目录、设备直通或虚拟机管理 API。
