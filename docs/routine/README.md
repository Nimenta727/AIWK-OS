# AIWS Routine / 开发例行记录

每次仓库修改需要独立的时间戳文件，包含变更摘要、影响文件、验证结论、已知问题与下一步。历史记录按文件名时间顺序存放在本目录；此索引仅展示最近系统级新方向，不覆盖之前的 75 条历史记录。

Each repository modification requires a timestamped log with changed files, verification, limitations and next steps. Earlier entries are retained intact.

- [2026-11-20 21:30 — 独立 AIWS OS 客户机工程 / Independent guest OS bootstrap](2026-11-20_2130-aiws-os-guest-bootstrap.md)

- [2026-11-20 22:26 — C#/Swift 跨平台代码智能索引 / Code intelligence MVP](2026-11-20_2226-code-intelligence-static-index.md)
- [2026-11-20 22:32 — XAML 类型映射与 XML 安全 / XAML link and XML hardening](2026-11-20_2232-xaml-xml-hardening.md)
- [2026-11-20 22:36 — CI 28/28 验证与后续计划 / Verified regression and next steps](2026-11-20_2236-code-intelligence-ci-verified.md)

- [2026-11-20 23:01 — Linux 工作台服务 / Guest controller](2026-11-20_2301-os-workbench-controller.md)
- [2026-11-20 23:08 — 共用 React Linux 模式 / Shared frontend](2026-11-20_2308-react-workbench-linux-mode.md)
- [2026-11-20 23:17 — Debian GUI 与工作台系统集成](2026-11-20_2317-debian-desktop-workbench-guest-boot.md)
- [2026-11-20 23:24 — NixOS 声明式系统配方](2026-11-20_2324-nixos-declarative-adapter.md)
- [2026-11-20 23:29 — 真实 ISO 与 QEMU 启动 CI](2026-11-20_2329-os-real-image-qemu-boot-workflow.md)

- [2026-11-21 00:53 — 只允许客户机的权限隔离 / Guest only](2026-11-21_0053-guest-only-host-deny-boundary.md)
- [2026-11-21 00:57 — P0/P1 强制验收清单与挂载检查 / Priority gates](2026-11-21_0057-host-boundary-p0-p1-acceptance.md)
- [2026-11-21 01:01 — 客户机文件服务与哈希前置条件 / Guest file API](2026-11-21_0101-workbench-guest-file-api.md)
- [2026-11-21 01:04 — Linux 工作台文件结构浏览 / Guest file UI](2026-11-21_0104-guest-files-visual-ui.md)

- [2026-11-21 01:20 — 客体持久化 DAG 与审计 / Persistent task store](2026-11-21_0120-guest-tasks-dag-persistence.md)
- [2026-11-21 01:25 — 本地模型结构化建议服务](2026-11-21_0125-local-model-offline-planner-gateway.md)
- [2026-11-21 01:32 — 模型与 DAG 统一工作台 API](2026-11-21_0132-task-http-local-model-integration.md)
- [2026-11-21 01:40 — DAG/审批与离线小模型界面](2026-11-21_0140-task-dag-local-model-ui.md)
- [2026-11-21 01:50 — AIWS 默认系统 Shell 与 GUI 点击测试](2026-11-21_0150-aiws-kiosk-shell-gui-acceptance.md)
- [2026-11-21 02:00 — 客体离线模型运行器](2026-11-21_0200-local-model-guest-service.md)
- [2026-11-21 02:05 — 专用模型合成数据与离线评估](2026-11-21_0205-local-model-dataset-evaluation.md)
- [2026-11-21 02:12 — Guest LoRA 训练配方](2026-11-21_0212-guest-offline-lora-training-recipe.md)
- [2026-11-21 02:16 — 拒绝主机训练数据读取](2026-11-21_0216-lora-train-guest-data-guard.md)

- [2026-11-21 02:26 — 本地模型从工作台受控启停](2026-11-21_0226-local-model-workbench-toggle.md)

- [2026-11-21 02:35 — 客户机系统服务与内核候选版本控制](2026-11-21_0235-guest-service-kernel-candidate-core.md)
- [2026-11-21 02:43 — 系统服务、内核与模型计划统一 DAG](2026-11-21_0243-unified-guest-services-kernel-model-dag.md)
- [2026-11-21 02:51 — 中断重新审批与审计完整性](2026-11-21_0251-guest-dag-recovery-audit-integrity.md)
- [2026-11-21 03:00 — 系统服务/内核可视化页面](2026-11-21_0300-system-service-kernel-console.md)
- [2026-11-21 03:09 — 模型版本导入、SHA 校验与回滚](2026-11-21_0309-guest-model-versioned-provisioning.md)
- [2026-11-21 03:16 — 模型启动前强制权重完整性检查](2026-11-21_0316-model-registry-startup-integrity-gate.md)
- [2026-11-21 03:22 — 本地模型一键生成待执行 DAG 与数据目录保护](2026-11-21_0322-model-to-dag-state-boundary-hardening.md)
- [2026-11-21 03:28 — QEMU 内核候选图形验收](2026-11-21_0328-guest-gui-kernel-candidate-acceptance.md)
- [2026-11-21 03:36 — AI 原生工作台整合架构及验收界限](2026-11-21_0336-aiws-guest-agent-model-kernel-architecture.md)

- [2026-11-21 09:14 — QEMU kernel stage debug](2026-11-21_0914-qemu-kernel-stage-diagnostics.md)
- [2026-11-21 09:18 — Kernel DAG dispatch root cause](2026-11-21_0918-kernel-dag-dispatch-root-cause-fixed.md)
- [2026-11-21 09:29 — Independent systemd guest Agent](2026-11-21_0929-standalone-guest-systemd-agent.md)
- [2026-11-21 09:34 — Workbench over Unix IPC](2026-11-21_0934-workbench-to-systemd-agent-ipc.md)
- [2026-11-21 09:39 — Guest Agent boot health guard](2026-11-21_0939-agent-workspace-and-systemd-boot-health.md)
- [2026-11-21 09:48 — Guest-only UEFI A/B manager](2026-11-21_0948-guest-systemd-boot-ab-manager.md)
- [2026-11-21 10:01 — Actual OVMF B-to-A fault test](2026-11-21_1001-uefi-firmware-ab-fault-injection.md)
- [2026-11-21 10:09 — Real Qwen2B CPU inference](2026-11-21_1009-real-qwen-2b-cpu-smoke-workflow.md)
- [2026-11-21 10:16 — Approved file edits via DAG](2026-11-21_1016-unified-file-write-and-durable-agent-queue.md)
- [2026-11-21 10:22 — Read-only files via Agent IPC](2026-11-21_1022-unified-readonly-files-through-agent-ipc.md)
- [2026-11-21 10:31 — UEFI guest boot manager package](2026-11-21_1031-guest-efi-boot-manager-packaging.md)
- [2026-11-21 10:40 — GGUF guest registry preload](2026-11-21_1040-bundled-model-guest-registry.md)
- [2026-11-21 10:44 — Optional model-inclusive ISO](2026-11-21_1044-optional-offline-model-debian-image.md)
- [2026-11-21 10:49 — Read-only bundled GGUF verification](2026-11-21_1049-zero-copy-bundled-gguf-verification.md)
- [2026-11-21 10:56 — Real QEMU guest model inference test](2026-11-21_1056-real-guest-qemu-local-2b-inference.md)
- [2026-11-21 11:00 — Documentation and verification gate sync](2026-11-21_1100-gates-unified-agent-boot-model-docs.md)

- [2026-11-21 11:07 — 修复真实小模型容器文件权限](2026-11-21_1107-model-container-permission-fix.md)
- [2026-11-21 11:14 — 修复 UEFI 文件路径预检兼容性](2026-11-21_1114-uefi-firmware-discovery-preflight.md)
- [2026-11-21 11:23 — 在 QEMU 中强制验证独立 Agent 与 UI 服务重启恢复](2026-11-21_1123-guest-agent-ui-lifecycle-qemu-smoke.md)
- [2026-11-21 11:28 — 本轮真实 CI 结果与严格验收边界](2026-11-21_1128-verified-ci-results-and-open-gates.md)

- [2026-11-21 11:35 — 真实模型加载故障 stderr/ldd 诊断](2026-11-21_1135-real-model-loader-stderr-diagnostics.md)
- [2026-11-21 11:44 — 小模型启停也必须经过持久 DAG 审批](2026-11-21_1144-model-service-lifecycle-reviewed-agent-dag.md)
- [2026-11-21 11:50 — 恢复模型 DAG 保存入口和动态模型开关](2026-11-21_1150-repair-model-plan-and-live-status.md)

- [2026-11-21 11:55 — SQLite 任务状态和审计原子事务](2026-11-21_1155-atomic-agent-state-audit-transitions.md)
- [2026-11-21 12:00 — QEMU Agent/UI 重启恢复验收通过](2026-11-21_1200-qemu-agent-lifecycle-verified.md)

- [2026-11-21 12:07 — 修复 Qwen 推理 GLIBC 编译目标不一致](2026-11-21_1207-debian13-llama-abi-build.md)
