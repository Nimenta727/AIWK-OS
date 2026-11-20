# 2026-11-20 19:40 — 总控台原子审批与本地调度队列交互

## 修改与理由
- 新增 `WorkstationController.ApproveAndQueueStage`，在同一持久化事务内完成一次性阶段审批与本地排队；任何校验失败都回滚批准状态和票据，绝不会在此操作中启动 CLI。
- 扩充 WPF allowlist：`scheduler.prepare` 只路由至受限控制层，仍由原生串行写入门控执行。
- 总控台将两步点击合并为一次「审批并加入调度队列」；之后独立显示「确认启动官方 CLI」，沿用 Windows 原生确认、工作区校验与本地 Token 预算。
- 补充 .NET smoke 测试：成功排队无模型调用、重复操作回滚、用户可取消票据。
- 更新 `docs/UNIFIED_ORCHESTRATION_V18.md` 和本 routine 文件。

## 检验
- V1.8 首轮 Windows CI #44728087451 失败：App.tsx `snapshot` 空值编译问题；已由上一修复提交 4604cbb 修正。
- V1.8 第二轮 Windows CI #44728393607 已通过 React、WPF/.NET、核心 smoke 与 x64 打包；本次交互增强需要新 CI 再验证。
- 当前本地 Node 逻辑测试 29/29、Python 回归 38/38 通过；.NET 新增测试等待 Windows CI。

## 尚存边界
- 队列不能后台调用 Claude/Codex；没有操作系统权限沙箱，也未承诺可观察 CLI 内部模型请求。
- 正式签名安装程序、Hyper-V GUI 和 ACL 实测、独立 Windows Worker、经许可的无人值守 Provider Adapter 均未完成。

## 下一步
1. 验证新增原子审批和总控台按钮的 Windows CI，生成可下载整包。
2. 使用真实 Hyper-V 普通账户对任务排队、跨重启、Worktree、ConPTY、审查与计划视图做人工验收。
3. 完成独立 IPC Broker / 最小权限 Worker 后，才研究受官方支持的自动 Agent 执行与事件回收。
4. 按 docs/routine 持续记录每次 GitHub 代码变更和回归证据。
