# V1.7 — AI 调用与项目结构双向可视化 / Execution Atlas

**状态：Windows CI [44704423770](https://github.com/Nimenta727/Windows-AI-Workstation/actions/runs/44704423770) 已通过，EXE 与离线 UI 打包已核验；用户 Hyper-V GUI 验收尚未进行。**

## 产品目标与位置

桌面侧边栏新增 **AI 调用与结构** 页面，取代“只能分别去调用追踪和文件树找证据”的体验。

- 左侧：任务 → Agent 阶段 → 执行器分配、上下文准备、CLI 启动、模型/工具事件、结果交接；用户导入的官方结构化事件按序展开。
- 右侧：同一阶段前后目录快照的 **结构差异 / 修改前 / 修改后** 三种可展开树，显示目录、文件、影响范围、Git 确认的重命名。
- 下方：点击文件可查看未提交 Git Diff；若已提交则使用受限 `git diff <beforeHEAD> <afterHEAD> -- <file>` 展示历史代码差异；点击变更文件会反向查询关联的阶段。
- 右下：点击流程节点显示证据和用量口径；用户明确点击后才显示 AIWS 生成的本地交接草稿、来源分解和预估 Token。

## 数据与证据等级

| 数据 | 来源 | 不能断言 |
| --- | --- | --- |
| DAG 阶段、审批与启动 | AIWS 本地状态/事件账本 | 不等于发送了模型 HTTP 请求 |
| Codex 回合/工具与 Claude 汇总 | 用户选择的官方格式日志导入结果 | 不等于平台实时抓到所有模型内部事件；日志真实性并未独立认证 |
| Token 输入、输出、缓存 | 成功导入的结构化日志 | 没有日志时必须标“未知”，不能写成零或按字符计算真实计费 Token |
| 上下文草稿与约数 | HandoffBuilder 的本地、可查看草稿 | 不包括 CLI 内部自建提示词、隐藏工具 schema、缓存上下文 |
| 文件结构前后 | ProjectWorkspaceService 的阶段开始/完成本地快照 | 文件存在变化不能证明 Agent 是作者；中途修改又撤销可能漏报 |
| 文件修改/提交 | Git 状态、签名、HEAD 提交路径 | 仅时间关联，无法认定是哪一条模型请求所致 |
| 文件移动/重命名 | Git `--find-renames=50%` 所确认的提交路径 | 未提交情况下不会凭文件名相似度推断重命名 |

**注意：** Git 本身不跟踪目录。所谓目录新增/删除为两个受限文件系统清单的对比。`node_modules`、`.git`、编译缓存等目录排除在扫描之外，符号链接不会跟随。达到 2,500 路径/10 层上限、读取失败或原有旧任务缺少快照时，界面显示“部分/未知”，不会从缺失推断删除。老任务的 V1.2/V1.6 检查点不具有 `TreeCaptured`，需要通过新版本完成一个阶段才会积累可比较数据；不需要重置任务库。

## 后端 API：WebView2 受限桥接

| action | 类型 | 权限边界 |
| --- | --- | --- |
| `atlas.flow` | 读 | 投影 AIWS 任务阶段及显式导入的模型用量事件，不发送模型请求 |
| `atlas.structure` | 读 | 读取当前任务某阶段本地 Worktree 的起止结构、Git 证据；运行阶段只读现场快照 |
| `atlas.fileStages` | 读 | 用当前文件的相对路径反查任务阶段，最多检查前 40 个阶段，证据缺失时明确标部分 |
| `atlas.fileDiff` | 读 | 受限 Git 单文件 Diff；已提交使用两完整 HEAD SHA；路径/敏感文件受保护 |
| `atlas.context` | 读（点击触发） | 在内存中重建当前阶段本地交接草稿，正文最多显示 24,000 字符，不写日志或自动发送 |

WebView2 原生桥接既有源验证仍适用；不提供 Shell、Git 写操作、模型凭据或系统提权的新接口。**单纯打开此页面不会产生模型 Token**。所有解析和 Diff 在 VM 内完成，敏感文件的显式预览限制沿用 V1.2 规则。

## 数据结构与兼容性

- `GitCheckpoint` 新增 `Tree: StructurePath[]`、`TreeCaptured`、`TreePartial`，保存路径与目录布尔值，不保存文件内容。保留原有 `Files`、`Head`、`Partial` 与时间戳；老 JSON 无新字段时默认为无结构证据。
- `WorkspaceEvolutionService.StructureReport` 保存每个路径的 `before`、`after`、`change`、`evidence`，并按目录聚合变更计数；移动只在 Git 明确确认时带路径映射。
- `ContextInspector.ContextReport` 基于实际 `HandoffBuilder.Prepare` 返回已用字符、约数、分段来源与截断警告，绝不标记为模型实际发送的 tokens。
- `TaskRepository` 对目录清单增加数量与相对路径验证。旧版任务仍可读取；不静默生成过去未存在的目录清单。

## 验收矩阵

1. **逻辑**：结构树按父目录聚合、深层筛选、新增/删除、未知/缺失证据显示；新测试覆盖纯数据投影。
2. **真实仓库**：阶段开始/完成截取目录树、修改、删除、新建模块，两个提交 HEAD 之间 Git 历史 Diff、已提交路径关联；不改动 Git index。
3. **兼容**：旧 V1.6 任务和未开始阶段不出现假的“0 文件变更”；旧 JSON 文件原样迁移并可读取，失效路径被拒绝。
4. **Windows 编译**：Node 测试、TypeScript + Vite、.NET 核心 SmokeTests、WPF 编译以及 EXE+`ui-dist` 打包，必须以 GitHub Windows CI 成功为证。
5. **Hyper-V 实机**（待用户验收）：运行有历史任务和新任务的 EXE，验证高 DPI、中文路径、大仓库、Worktree 区别、Git 重命名、ConPTY 可切换、完成后重启仍能查看前后树和 Diff。

## 未实现与下一步

- 目前不是任意 Claude/Codex 内部 HTTP 请求的完整树：官方 CLI 不提供的内部调用无法凭 GUI 进程启动还原；须在受支持的结构化接口范围内扩大真实请求可观测性。
- 没有行级 Agent 作者证明，也没有逐 hunk 批准/自动回滚。下一轮需要在隔离执行 Worker 中记录可信的工具操作身份，完善权限隔离与事件去重。
- 大仓库结构树仍采用有上限的路径列表，后续增加增量快照、搜索索引、虚拟化树和数据压缩。
- 当前版本继续使用 AIWS 自己的 React UI 和 WPF/.NET 执行核心，未嵌入完整 T3/OpenClaw/Kandev 软件。

**English summary:** V1.7 adds an offline, evidence-graded Execution Atlas: expand workflow and imported provider events, inspect locally prepared context, compare per-stage directory snapshots before/after, open Git diffs, and navigate both ways between stages and files. Missing telemetry or legacy snapshots are explicitly unknown. This is not a model proxy, a token billing meter, or a proof of AI authorship.
