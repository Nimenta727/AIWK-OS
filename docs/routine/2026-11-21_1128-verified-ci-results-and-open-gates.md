# 2026-11-21 11:28 — Current CI receipts, accepted fixes and incomplete hard gates

## 已有实证
- GUI 故障从 QEMU 真实任务日志定位为 kernel.stage 被旧普通 toolplane 调用；Python/Windows/static 以及至少一个修复后的 Debian/QEMU 基础工作台测试已通过。独立 Agent 与 UI 重启恢复的更严格新版本仍须再次验证。
- 真实 llama.cpp 编译与 GGUF SHA 校验已在 run 44850313856 成功执行，但模型容器拒绝脚本读取，故此运行的真实推理为失败，下一次修复工作流尚未完成。
- 真实 OVMF B/A 首次尝试 run 44850151109 未到固件启动阶段即预检退出；已修复跨 Ubuntu 版本路径发现，最新带 [ab-boot] 的 workflow 尚未通过。

## 文档修改
- docs/routine/README.md 增加 1107、1114、1123 和本次记录。
- docs/AIWS_OS_PRIORITY_GATES.md 明确实证和未知边界。
## 下一步
重点等待最新同提交 CI 证明：Debian/QEMU 的 GUI+kernel candidate+Agent 生命周期，OVMF 的真实 B→A 回退及模型 networkless CPU/QEMU 真实推理。代码已落地不等于通过这些验收；对于任何失败从串口、步骤日志做定点修复，不减少验收断言。
