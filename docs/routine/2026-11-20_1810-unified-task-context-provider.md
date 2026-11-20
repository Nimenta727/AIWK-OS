# 2026-11-20 18:10 — 统一任务内核、交接编译器、模型适配器

## 任务目标
完成 V1.7.3 统一 Agent 控制平面的前三阶段：统一任务与计划工件、减少重复上下文的 ContextCompiler、明确的 Claude/Codex/人工执行器能力契约。继续保留 AIWS 自己的 Windows EXE、工作流、Git、计划和可视化，不嵌入原版上游软件。

## 本次变更
- `UnifiedTaskCore.cs` 和 `Models.cs`：Task 追加 schema v1 统一目标、计划版本、WorkItem、AgentRun、Artifact 的本地持久化，WorkItem ID 与既有阶段 ID 对齐；数据结构不会存整份计划/源码。
- `TaskRepository.cs`、`WorkstationController.cs`：旧 JSON 兼容与验证、任务目标和验收标准、用户选择 Markdown 计划版本关联、Pending 阶段执行器切换、状态落盘与失败回滚。
- `ContextCompiler.cs`、`HandoffBuilder.cs`、`ContextInspector.cs`：结构化来源、稳定指纹、预算统一预检、交接引用与长度限制、显式查看完整草稿；避免每次自动转发所有历史。
- `ProviderAdapterRegistry.cs`：提供 Claude Code、Codex、Manual 能力声明与安全降级，不冒充无人值守接口或内部用量。
- `ModularWorkstationWindow.xaml.cs`、`bridge.ts`、`App.tsx`、`TaskInspector.tsx`、`PlanCenter.tsx`、新增 React 组件及样式：统一任务档案、计划绑定、模型切换和上下文来源展示。
- `.NET Core.SmokeTests/Program.cs`：旧任务迁移、真实计划读写哈希、交接确定性、执行器切换、审批恢复、完成工件与保存重载测试。
- `README.md` 和 `docs/UNIFIED_TASK_IMPLEMENTATION.md`：功能说明、接口、风险和验收边界。

## 质量与安全要点
- React 页面和本地文件/Git/计划图不应发起模型请求；只有人工确认后才可启动官方 CLI。
- 本地 Token 估算不代表 CLI 内部 Token 或订阅账单；本地 launch-intent 不是远程模型请求证据。
- 模型切换不复制任务，也不重用之前针对另一执行器的批准。
- 不引入 Kandev AGPL 源码或未标注许可的上游文件；本次新增 C# / React 代码由 AIWS 独立实现。
- 待 CI 验证后的提交记录应链接实际 Actions 运行号；Hyper-V GUI/进程隔离仍需手动验收。

## 下一步
1. 依据 Windows CI 的 React、WPF、.NET smoke 结果修复兼容性问题，并将成功的运行证据写入新的 routine 记录。
2. 使用真实 Windows 11 Hyper-V VM 验收计划绑定、未安装 CLI 的提示、实际模型切换、上下文预览和任务数据恢复。
3. 再实施受支持的 Agent 自动编排和独立 Windows 执行 Broker；不抓取订阅凭据。
4. 建立多模型交接基准，记录输入估算和可验证实际用量，避免未经实测声称固定节省比例。
