# 2026-11-20_1533 — V1.6 multi-agent-dag-orchestration

## 本次修改 / Changes
新增 DAG 模板、依赖校验、循环拒绝、可视化分支/汇合、节点添加/依赖编辑、独立 Worktree 并发保护和依赖定向上下文。

## 涉及文件 / Files
WorkflowGraph.cs, WorkflowEngine.cs, Models.cs, WorkflowDesigner.tsx, DagCanvas.tsx, HandoffBuilder.cs

## 验证 / Verification
- 38 项 Python 回归测试本地通过。
- 13 项 Node 前端模型测试本地通过。
- .NET Windows 编译和原生 ConPTY GUI 操作需以 CI / Hyper-V 实测为准，不宣称当前已验收。

## 风险 / Known risks
- Windows 工作区验证不能替代沙箱；官方 CLI 继承当前用户权限。
- 模型内部调用与实际用量可能未知；不能把 CLI 启动当作模型调用。
- Git 的时间关联并不能独立证明某次文件改动由 Agent 写入。

## 下一步 / Next steps
下一步使用官方支持的自动执行接口扩展 Agent 适配器；当前仍为显式批准后启动官方 CLI，不代理订阅凭据。
