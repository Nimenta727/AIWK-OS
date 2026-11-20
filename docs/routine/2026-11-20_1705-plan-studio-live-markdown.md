# 2026-11-20 17:05 — AIWS 计划中心：Markdown 展示与本地近实时更新

## 背景和目标
用户希望把 AI 生成的大量计划书变成易于阅读、可展开、可跟踪的计划平台，并实时看到执行进展。既有 V1.7 已具备调用与代码结构证据，但缺少统一计划文档界面。

## 本次代码变更
- 新增 `PlanWorkspaceService.cs`：只读扫描当前项目和 Agent Worktree 中约定位置的 Markdown 计划，校验工作区、安全相对路径、文件/目录符号链接、文档大小与更新时间；返回轻量文件清单和按需读取文档。
- `ModularWorkstationWindow.xaml.cs`：新增有界桥接操作 `plans.list` / `plans.read`，更新产品版本；不暴露任意路径或 Shell。
- React `PlanCenter.tsx`、`model/plan.mjs`：新导航和默认视图、分层计划大纲、卡片看板、阶段状态、清单进度、原文视图、项目 Worktree 切换及每 3 秒本地轮询。
- 新增 `tests/plan.test.mjs` 和 .NET 核心烟雾测试场景；更新前端类型、样式、README 与技术说明。
- 未修改 Claude Code/Codex 的账号认证方式，不会为了渲染计划而新增模型请求。

## 影响文件
- `desktop/AIWorkstation.Core/PlanWorkspaceService.cs`
- `desktop/AIWorkstation.Core.SmokeTests/Program.cs`
- `desktop/AIWorkstation.Desktop/ModularWorkstationWindow.xaml.cs`
- `desktop/AIWorkstation.Frontend/src/App.tsx`
- `desktop/AIWorkstation.Frontend/src/bridge.ts`
- `desktop/AIWorkstation.Frontend/src/components/PlanCenter.tsx`
- `desktop/AIWorkstation.Frontend/src/model/plan.mjs`
- `desktop/AIWorkstation.Frontend/tests/plan.test.mjs`
- `desktop/AIWorkstation.Frontend/src/styles.css`
- `desktop/AIWorkstation.Frontend/package.json`
- `docs/PLAN_STUDIO_V171.md`、`README.md` 及本日志。

## 验证
- 本地 Node 模型测试：26 项通过。
- 本地旧版 Python 测试：38 项通过。
- TypeScript/TSX 转译语法检查：通过；容器中的前端依赖安装超时，需以 Windows CI 的完整类型检查和 WPF 编译为准。
- GitHub Windows CI 与实际 Hyper-V GUI 验收应分别记录，不能互相替代。

## 已知限制
- 3 秒轮询只能反映项目中已写入的计划文件与 AIWS 本地任务状态，无法监控外部模型 CLI 未暴露的内部计划。
- 对没有 Markdown 勾选符号的计划，进度为“未知”。
- 阶段计划与 Markdown 条目尚无稳定的任务 ID 对应，不能假称逐条计划已经被 Agent 执行。
- 只读本地文件访问防护并非操作系统级沙箱；需避免以管理员身份打开不信任的仓库。

## 下一步规划
1. Windows CI 编译与 .NET 核心烟雾测试全绿，修复任何类型或运行时编译故障。
2. 在真实 Hyper-V Windows 虚拟机中查看多份计划文件的实时刷新、中文输入、离线状态和界面布局。
3. 增加经用户确认的长计划粘贴/持久化、修改版本对比及计划条目与执行事件的稳定双向链接。
4. 设计受支持的 Provider 计划事件适配器；继续保留“未知”的证据状态和最小权限原则。
