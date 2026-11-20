# 2026-11-20 19:10 — 统一 Agent 调度、总控台与可靠性加固

## 本轮目标
按用户要求，落实此前规划中的第 4 阶段 Agent 调度器、第 5 阶段统一可视化，以及第 6 阶段的可直接代码实现的稳定性和安全加固，并提供后续增强路线。基线为 V1.7.3 Windows 原生工作台。

## 实际改动
- `AgentScheduler.cs`：在原 DAG 上计算下一可执行阶段，检查依赖、审批、预算、执行器可用性和 Worktree 冲突；不为调度额外请求模型。生成不会自动启动 CLI 的持久化排队票据。
- `UnifiedTaskCore.cs` / `WorkstationController.cs`：持久化调度偏好/票据、限量验证、跨重启读取、主动撤销、切换/计划/目标变化时撤销旧票据，显式启动后消费票据；沿用现有任务状态权威和备份机制。
- `MissionControl.tsx` / `mission.mjs` / `App.tsx` / `bridge.ts` / `styles.css`：统一任务总控视图，计划、DAG、审批、上下文预估、Token 证据、Git 改动和诊断快捷联动；补充可用模型建议、双向导航和前端安全限制。
- `ModularWorkstationWindow.xaml.cs`：允许名单加上调度与诊断接口；原生窗口串行处理有副作用的调用，保留外部 CLI 二次确认。
- `WorkstationDiagnostics.cs`：本地诊断计数与明确点击才能导出的脱敏 JSON，不包含任务名、目录、提示词或模型凭据。
- `scripts/Test-HyperVAcceptance.ps1`：只读 Windows VM 发行包预检；不自动启动 EXE 或 Agent。
- `docs/UNIFIED_ORCHESTRATION_V18.md`：架构、能力范围、隐私、安全边界、验收标准和下一步。

## 测试结果
- 本地：Node 前端逻辑测试 29/29，通过；Python 回归 38/38，通过。
- 新增 .NET smoke：排队与审批、重复保护、跨重启、撤销、上下文更新作废旧票据、显式消费、禁止重播、敏感诊断字段排除。
- Windows CI / WPF / .NET / Hyper-V GUI：以提交后 Actions 实际结果为准；CI 未运行时不能声明成功。

## 限制与风险
- 当前交互式官方 CLI 没有经过认证的无人值守执行接口；调度器自动计算下一步，但不自动发送模型请求。
- 并行配置只影响推荐调度容量，OS 权限仍属于 Windows 用户，Git Worktree 不是沙箱。
- 正式独立执行 Broker、真实 VM GUI、代码签名、安装升级回滚和安全渗透测试未完成，不将 V1.8 预览版称为稳定 V2.0。

## 下一步
1. 完成 Windows CI 编译和行为测试，修复确定性错误，交付实际 x64 运行包。
2. 使用 `scripts/Test-HyperVAcceptance.ps1` 在普通账号的 Hyper-V VM 上手动验收 ConPTY、队列、重启及文件/计划联动。
3. 优先建设独立最小权限 Windows Worker / IPC，完成许可检查后再考虑官方支持的无人值守 Agent 路由。
4. 长期完善作业队列的持久进程身份、超时取消、导入官方用量、代码签名、安装/迁移及安全审计。
