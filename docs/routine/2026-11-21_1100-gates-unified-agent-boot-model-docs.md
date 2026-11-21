# 2026-11-21 11:00 — Routine index and accurate unified OS gates

## 本次修改
- 汇总 docs/routine/README.md 中本轮 15 组 GitHub 代码变更的独立例行记录，包含故障诊断、DAG 分发修复、独立 Linux systemd Agent、文件审批、客体 EFI A/B、真实固件故障注入、真实 Qwen2B CPU 基准、可选内置模型 ISO 与真正 QEMU guest 模型验收。
- 更新 README.md、os/README.md、docs/AIWS_GUEST_AGENT_SYSTEM_KERNEL.md 的架构：独立 AF_UNIX Agent 调度、read-only 工具、持久写入审批、bootloader root-only 管理和 GGUF SHA 管理。
- 区分已经完成代码、Python/Windows 静态测试、QEMU 正在进行和最后真正验收成功的严格不同状态。不存在任何宿主控制 API。
## 文件
README.md, os/README.md, docs/AIWS_GUEST_AGENT_SYSTEM_KERNEL.md, docs/routine/README.md, 本 routine。
## 下一步
核查全部 GitHub workflows，修复 QEMU/UEFI/model 实际故障。额外建设真实内核故障重启自动复原、全量模型评测、Windows DAG 完整协议、NixOS ISO 真构建启动。
