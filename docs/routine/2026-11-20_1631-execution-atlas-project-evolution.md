# 2026-11-20 16:31 (UTC+8) — V1.7 AI 调用与项目结构全景

## 本次目标
将此前独立的“模型调用/Token 追踪”和“文件/Git Diff”重组为一个可以逐层展开、双向定位的桌面视图。以 V1.6 原生桌面项目为基础，不额外请求模型。

## 改动内容
- 新增 `ExecutionAtlas.tsx` 和 `atlas.mjs`，包含五阶段调用证据树、导入 Provider 事件、Token/上下文检查器、目录前后树、路径筛选、逐文件 Diff 与反向阶段定位。
- 新增 `WorkspaceEvolutionService.cs`，比较两个阶段检查点的元数据目录清单及 Git 证据；目录状态包括新增、删除、修改、受影响、未知和 Git 确认的移动。
- `ProjectWorkspaceService` 在原有 Git 状态检查点之外保存上限 2500 的路径/目录清单，保持 V1.6 旧 JSON 兼容；不沿符号链接扫描、不存文件内容。
- `GitWorkspaceService` 支持受限历史单文件 Diff，并基于 Git `--find-renames` 记录真正的文件重命名映射，避免仅凭路径猜测移动。
- 新增 `ContextInspector.cs`，明确区分本地交接预览和 CLI 内部未知上下文，用户主动点击才会返回草稿。
- WPF 原生桥接新增 `atlas.flow/structure/fileStages/fileDiff/context` 白名单接口，保留已有任务、权限与 CLI 边界。
- 扩充 .NET 与 Node 回归测试，保持原有 Python 回归可运行；新增 V1.7 技术说明与 README 入口。

## 修改文件（主要）
- `desktop/AIWorkstation.Core/{ProjectWorkspaceService,WorkspaceEvolutionService,GitWorkspaceService,ContextInspector,TaskRepository}.cs`
- `desktop/AIWorkstation.Desktop/ModularWorkstationWindow.xaml.cs`
- `desktop/AIWorkstation.Frontend/src/{App.tsx,bridge.ts,components/ExecutionAtlas.tsx,model/atlas.mjs,styles.css}`
- `desktop/AIWorkstation.Frontend/{package.json,tests/atlas.test.mjs}`
- `desktop/AIWorkstation.Core.SmokeTests/Program.cs`
- `README.md`, `docs/EXECUTION_ATLAS_V17.md`, `docs/ROADMAP.md`

## 验证标准与限制
- Node 前端逻辑、Python 既有回归与新增的 Windows .NET 核心测试均要求通过；真正的 Windows EXE 可用性以 GitHub Actions 的 Windows 工作流为准。
- 旧任务没有前后目录快照必须显示未知；Git HEAD 变化、用户人工编辑与 Agent 运行不能自动归因为模型操作。
- 当前 API 只投影本地事件及用户导入的部分 Provider 事件，不拦截或还原 Claude/Codex 内部请求，不读取 OAuth 凭据。
- **此处代码提交不代表已完成用户 Hyper-V VM 的图形界面验收。**

## 下一步规划
1. 在实际 Hyper-V Windows 11 环境运行 V1.7，验证历史任务兼容、结构树筛选、历史 Diff、中文路径、高 DPI 与进程切换。
2. 对 `.gitignore` 屏蔽目录、Git 子模块和超大项目建立独立可配置扫描策略与增量索引。
3. 设计真实 Agent Tool event 与 Git 修改操作的可信关联，在权限受限的执行 Worker 中采集可校验身份，避免误判代码作者。
4. 完善逐 hunk 审查与恢复、模型调用结构化追踪、性能指标及自动 UI 验收。
5. 每次后续 GitHub 代码变更继续在 `docs/routine` 生成带时间、改动、验证和规划的记录。
