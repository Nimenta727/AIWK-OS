# 2026-11-20 17:45 — V1.7.2：Agent 本地交接预算、重复启动检查与轻量工作流

## 目的
基于用户关于“Agent 架构不能因流程消耗过多 Token”的要求，参考 T3 Code、OpenCode、Codex、Claude Code 的上下文管理机制，将 AIWS **自己可控的**交接文本预算下沉到执行核心。

## 修改内容
- `ContextBudgetPolicy.cs`：本地 handoff 估算、提醒/阻断门槛、重复指纹检测、无模型调用的只读预检。
- `Models.cs`：任务持久化的预算字段；新增 lean 单 Agent + 人工验收工作流。
- `WorkstationController.cs`：`Preflight`、`SetPromptBudget`；在剪贴板、Git 快照和 CLI 启动前验证估算上限；重复交接要求明确确认；变更失败回滚预算字段。
- `TaskRepository.cs`：持久化时验证预算范围。
- `ModularWorkstationWindow.xaml.cs`：限定 WebView2 动作 `steps.preflight`、`tasks.setPromptBudget`，原生用户确认展示真实预检结果。
- React `TaskInspector.tsx`、`bridge.ts`、`App.tsx`、`styles.css`：预算面板、告警/拦截、轻量模板默认值。
- 核心 SmokeTests：大指令、重复上下文、阈值验证、不复制、不启动、保存和重开。
- `AIWorkstation.Desktop.csproj` 与前端 `package.json` 版本统一为 V1.7.2。
- 新增 `docs/TOKEN_EFFICIENCY_V172.md`，更新 README，说明技术来源、局限和测试门槛。

## 验证
- Python 回归 38 项通过；Node 本地逻辑测试 26 项通过。
- 当前环境无完整 .NET SDK；Windows CI 原生编译、Smoke 与 EXE 发布状态以 GitHub Actions 为准。前端 TypeScript/Vite 需要在 CI 安装依赖编译，不能仅凭本地无依赖环境认定通过。
- 未进行用户 Hyper-V 虚拟机中的真实 CLI/GUI 实测。

## 风险
- 所有阈值都是本地字符估算，不是模型内部/订阅 Token 硬限制。
- 复杂任务可以选择多 Agent，不能因节流而删除重要用户指令。
- 外部 CLI 会继承自己的缓存、工具输出、系统指令和会话策略；AIWS 不提取任何账号令牌。

## 下一步
1. 让 Windows CI 通过编译和新 SmokeTests，检查交接预算窗口实际运行。
2. 评估官方受支持的结构化流接口实现真实 token/工具事件计数。
3. 为文件上下文构建局部引用 manifest，减少重复全文读取与多 Agent 交接。
4. 在 Hyper-V 中验证真实行为并通过固定任务质量基准评估节流效果。
