# 2026-11-20_1533 — V1.5 execution-event-ledger

## 本次修改 / Changes
新增持久化执行事件（事件 ID、任务/阶段/运行标识、证据等级）和 UI 时间线；旧任务 JSON 可加载。

## 涉及文件 / Files
ExecutionLedger.cs, TaskRepository.cs, WorkstationController.cs, ExecutionTimeline.tsx

## 验证 / Verification
- 38 项 Python 回归测试本地通过。
- 13 项 Node 前端模型测试本地通过。
- .NET Windows 编译和原生 ConPTY GUI 操作需以 CI / Hyper-V 实测为准，不宣称当前已验收。

## 风险 / Known risks
- Windows 工作区验证不能替代沙箱；官方 CLI 继承当前用户权限。
- 模型内部调用与实际用量可能未知；不能把 CLI 启动当作模型调用。
- Git 的时间关联并不能独立证明某次文件改动由 Agent 写入。

## 下一步 / Next steps
下一步对接支持的结构化 CLI 工具事件，补充事件导入幂等键与日志保留策略。


---

## 双语历史编目 / Bilingual historical capsule (2026-11-20)

- 中文：本次档案主题为 **2026-11-20_1533 — V1.5 execution-event-ledger**，保留此前变更、测试结果、局限和当时的下一步计划。此追加说明不重新验证历史结论。
- English: This dated record concerns **execution event ledger**. Its earlier changes, tests, caveats and next steps are preserved. This appended synopsis is not a new verification.
- [历史时间线 / Log index](README.md) · [当前发行 / Current release](../../README.md)
