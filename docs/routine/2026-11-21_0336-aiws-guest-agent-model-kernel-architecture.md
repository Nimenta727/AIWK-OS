# 2026-11-21 03:36 — Synchronize architecture, release gates and routine history

## 文档修改
- 新增 docs/AIWS_GUEST_AGENT_SYSTEM_KERNEL.md，精确记录内置小模型（可选）、SQLite DAG/审批/审计、guest systemd 固定白名单、可撤销的内核候选快照、模型 GGUF hash 注册/版本回退及主机零控制边界。
- README.md 与 docs/README.md 新增架构入口；docs/AIWS_OS_PRIORITY_GATES.md 保留四项 P0/P1 里程碑但更新最新实现和未验收项。
- docs/routine/README.md 汇总本轮每次 GitHub 修改与下一阶段路径，完整留存历史文件不删除。
## 已知限制
Qwen3.5-2B 真正权重没有内置/加载、无 LoRA 完成证明；AIWS kernel stage 不支持真实部署与 A/B 启动回滚；NixOS 仍未实构建 boot。新系统页、内核候选 GUI 点击的 QEMU 验收以 CI 独立结果为准。
## 下一步
完善版本/许可 pinning、真正 guest-only 模型基线和资源测量；验证真实内核候选 GUI 与 crash recovery；NixOS 镜像，随后受控 kernel A/B 恢复。
