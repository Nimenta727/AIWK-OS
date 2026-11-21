# Windows → Linux Unified Agent 历史投影 / Safe Migration Projection

**Status / 状态：** 历史导入只读、不能执行；自动化 Windows 工具到 Linux 工具映射尚未发布。

## 实际链路

Windows WorkTask JSON（用户在 guest 中选文件） → 客体 HTTP /api/v1/tasks/import/windows → AF_UNIX 独立 systemd 用户 Agent → 唯一 GuestTaskStore SQLite → 工作台 DAG 历史视图。

导入后的每个旧阶段 **state=unmapped，tool=windows.unmapped，approval=0**。Windows 原有审批记录不能继承为 Linux 审批，Completed 也不能满足新的 Linux DAG 依赖；任何导入源指令都不会执行。

| Windows 源 | Linux 只读映射 | 数据保护 |
| --- | --- | --- |
| WorkTask / WorkflowStep | 任务 GUID、标题/goal、步骤 GUID、dependsOn、原 Agent/Status、原审批标记 | Linux runtime 永远 unmapped |
| UnifiedTaskState.Plans | planRevisions 的 id、SHA256、LinkedAt、RelativePath 哈希 | 不导入 Markdown 文本/真实路径 |
| UnifiedTaskState.WorkItems | workItems 的 id/stageId、Agent/Status、dependsOn、sourceStagePresent | 仅反映历史 |
| UnifiedTaskState.AgentRuns | agentRuns 的 run/stage ID、Agent/Status、Evidence、StartedAt/CompletedAt、AdapterId 哈希 | 不保留 prompt、token、CLI 原文 |
| WorkTask.ExecutionRecords | executionRecords 的 id/stage/run ID、kind、Evidence、At、Source 类别、Metadata SHA256 | 不保留 Metadata、终端记录 |
| Artifacts | kind + ContentHash | 不读源文件 |
| Import receipt | sourceSha256、evidenceSha256 与本地 audit 哈希链关联 | 仅检测普通篡改，不声称抗 guest root |

WorkflowStage projection 列出旧 ID、依赖、原 status/agent、Linux unmapped/executable=false；该投影与原 Agent 执行记录同存于一份 SQLite 状态数据库，而不是再造一个调度器。

## 数据安全与一致性

- Window 的 Agent 执行事件可标为 local-intent，并非官方 Provider 请求已真实发生的证明。
- 原系统的指令、结果和 Metadata 仅可用 SHA 标识；导入不提权、不复用源审批、不重新执行。
- 一次导入和导入审计收据在一个 SQLite 事务中完成；重启后读取再次核验完整 evidence digest。
- 数据库与本地 hash chain 不能对抗拥有 guest root 并能重写整个存储的攻击者；这是限界完整性检查，不是硬件可信证明。
- 不允许将 Windows 导入的私人内容直接用于 LoRA 或评测样本；独立模型微调标准参见 AIWS_MODEL_FINETUNING_STANDARD.md。

## 下一阶段 / Not implemented yet

1. 在 GUI 里为源 stage 显示源证据，用户逐项选择新 guest-only allowlisted tool 和独立的最小参数，而不是翻译旧 shell 指令。
2. 每个同意迁移的阶段创建**新的** Linux Task/StageRun/Approval，保留旧 Windows unmapped 历史不可变；不存在 silent replay。
3. 在 audit 存储源 ID→新 ID、工具版本、参数哈希、批准人、撤销证据；失败后回退新任务，不触碰历史。
4. 在真实 QEMU guest 中重复导入、查看计划版本和运行/执行时间轴，并在 Agent/UI 重启后比对数据完整性，再评估多 Agent 调度与批量导入。

**English:** Windows stages are strictly historical; no Windows execution or approval grants Linux authority. Plan, run, work-item and execution evidence are stored as bounded projections with hashes and provenance labels.
