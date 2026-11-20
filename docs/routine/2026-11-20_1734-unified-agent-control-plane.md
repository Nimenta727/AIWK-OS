# 2026-11-20 17:34 — 明确统一 Agent 控制平面目标

## 本次变更
- 根据用户澄清，将 AIWS 产品定位明确为“统一任务控制平面”，不再以“多模型聚合展示”作为最终目标。
- 新增 docs/UNIFIED_AGENT_CONTROL_PLANE.md：描述单一事实来源、上下文工件、模型切换、按需路由、受控 handoff、统一可视化与验收标准。
- 更新 README 与 docs/ROADMAP.md 的设计入口，避免今后只堆叠 Agent 界面却忽略任务与上下文交接。
- 本提交仅调整产品技术设计与开发优先级，不宣称已实现 ContextCompiler、自动 Scheduler 或官方内部请求全量监测。

## 影响文件
- README.md
- docs/ROADMAP.md
- docs/UNIFIED_AGENT_CONTROL_PLANE.md
- docs/routine/2026-11-20_1734-unified-agent-control-plane.md

## 验证和现状
- 查阅 main 的 WorkstationController、WorkflowGraph、HandoffBuilder、ContextBudgetPolicy、ExecutionLedger、Models 和 ROADMAP。
- V1.7.2 本地预算预检和 lean 模板已在源码存在；真正的统一上下文工件系统与多模型自动调度尚待实现。
- 文档修改不需要伪称完成 Windows 编译；运行代码保持不变。V1.7.2 的 CI 结果须单独核对。

## 后续计划
1. 设计统一 ArtifactRef / ContextManifest / HandoffBundle 的 schema 与旧数据迁移测试。
2. 以本地确定性策略实现 Agent 路由与 handoff 上下文预览，避免额外路由模型调用。
3. 引入 ProviderCapability 与官方接口支持等级，未支持自动化的 CLI 保持人工确认。
4. 将计划中心、请求证据树、Git 结构变化连接到统一任务和阶段 ID。
5. 执行 Windows CI 与 Hyper-V 实机验证，再评估实际 Token 节省和任务成功率。
