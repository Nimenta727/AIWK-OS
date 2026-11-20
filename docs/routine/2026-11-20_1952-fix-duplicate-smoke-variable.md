# 2026-11-20 19:52 — 修复原子审批 smoke 重复测试声明

## 问题及证据
GitHub Native Windows Desktop EXE #44729014971 的前端和 WPF 核心编译已成功，但执行 core smoke 时 C# 报错 `CS0128`：`Program.cs` 中局部变量 `oneClickPath` 重复声明；这是测试代码块插入重复导致的。

## 修改
- 仅删除第二个重复的审批+排队+撤销测试块，保留第一组和后续跨重启测试。
- 未改变调度业务逻辑、CLI 执行边界、前端界面或数据 schema。
- 在 docs/routine 留下失败来源和修复记录，以 GitHub Windows CI 后续真实结果为准。

## 当前验收与下一步
- Node 29/29 和 Python 38/38 已在本地通过；新 .NET smoke 的最终结论需本修复的 Windows CI。
- 若后续测试失败，继续修复并留存新 routine 日志；成功后核实 EXE、ui-dist 和压缩包。
- Hyper-V GUI、进程生命周期/ACL、独立 Worker、无人值守执行支持、代码签名与安装器仍待实际验收。
