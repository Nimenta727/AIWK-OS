# 2026-11-20_1533 — V1.3 per-agent-git-worktrees

## 本次修改 / Changes
新增 GitWorktreeService，按阶段创建独立 Git worktree/分支并记录基线；阶段项目树和 Git 检查点使用对应工作区；拒绝覆盖和非 Git 根目录。

## 涉及文件 / Files
GitWorktreeService.cs, Models.cs, WorkstationController.cs, ProjectExplorer.tsx, TaskInspector.tsx

## 验证 / Verification
- 38 项 Python 回归测试本地通过。
- 13 项 Node 前端模型测试本地通过。
- .NET Windows 编译和原生 ConPTY GUI 操作需以 CI / Hyper-V 实测为准，不宣称当前已验收。

## 风险 / Known risks
- Windows 工作区验证不能替代沙箱；官方 CLI 继承当前用户权限。
- 模型内部调用与实际用量可能未知；不能把 CLI 启动当作模型调用。
- Git 的时间关联并不能独立证明某次文件改动由 Agent 写入。

## 下一步 / Next steps
下一步验证真实仓库中的 Worktree 隔离与路径检查，完善逐 hunk 审查；目前不自动清理或推送。
