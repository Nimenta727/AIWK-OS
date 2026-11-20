> **双语导读 / Bilingual overview (2026-11-20)**
>
> 中文：统一 Agent 任务控制平面、交接协议与执行边界。保留历史正文及原始测试/风险描述，不能据此宣称现版已通过新的 Hyper-V 运行验收。
>
> English: Unified agent task control plane, handoff protocol and execution boundaries. The historical narrative and original test/risk statements remain intact; this is not evidence of fresh Hyper-V acceptance.
>
> [总索引 / Docs index](README.md) · [当前发行 / Release](RELEASE_NOTES_V19.md)

---

# AIWS 统一 Agent 控制平面：任务、上下文与模型调度

> 产品北极星（2026-11-20） · 设计与后续实现计划，**不是**声称已完成自动多 Agent 调度。
>
> One task, one durable source of truth; many interchangeable model executors.

## 0. 用户真正需要解决的问题

传统聊天客户端将状态绑定到单个对话或模型：Claude 规划、Codex 编码、其他模型复核时，用户必须搬运计划、历史、文件变化和结果；每次交接可能重新扫描仓库、重复解读任务、造成冗余 Token。即使界面展示多个 Agent，也未必存在统一任务管理。

**AIWS 的任务不在模型里，模型在 AIWS 的任务里。**

用户只需创建一次任务。AIWS 负责保留目标、约束、计划、阶段状态、相关文件、审批、Git 证据、上下文来源和可证实的 Token 记录。Agent 只是可替换的执行器。UI、任务管理器、计划中心、模型调用树和文件结构视图必须从同一份任务事实构建。

不是：多个 Chat 窗口 + 简单的模型切换下拉框 + 手工复制粘贴。
而是：任务工作台 + 统一调度 + 按需编译上下文 + 受控交接 + 可追踪结果。

## 1. 核心原则

1. **任务为中心**：Project / Task / PlanRevision / WorkItem / StageRun 都有稳定 ID 和可恢复的状态。模型/供应商不会拥有任务的唯一副本。
2. **上下文为工件**：保存可靠的任务目标、用户确认的约束、文件引用、Git 基线、阶段产物、已作决策；不把任一供应商的聊天记录当作全局权威上下文。
3. **模型为执行器**：按能力、用户偏好、授权方式和当前任务复杂度选择 Claude Code、Codex 或人工节点；可在阶段之间切换，不要求复制整个会话。
4. **交接为协议**：每次 handoff 传目标 + 与当前阶段有关的增量 + 工件引用 + 预期输出 + 预算 + 权限，不传默认完整聊天历史。先本地生成并可预览，之后才启动受支持的官方工具。
5. **证据为真实来源**：分清计划、GUI 操作、CLI 进程、官方结构化模型事件、Git 观察结果以及未知内部活动。只有强证据才可以归因为某个 Agent 写入文件。
6. **执行为受控动作**：工作区隔离、审批、重复调用防护、超时/取消/失败恢复；模型不得仅靠自然语言自行扩大权限。
7. **默认节约**：简单任务 1 Agent + 人工验收，不为分工而强制产生多轮模型调用；纯本地观察与展示不发送模型请求。

## 2. 五层架构与单一事实来源

| 层 | 拥有的数据或职责 | 不应负责 |
| --- | --- | --- |
| Workbench/UI | 一条任务的对话、计划看板、DAG、调用证据、文件/架构变化、审批交互 | 决定业务状态或直接执行任意命令 |
| Orchestration Core | Task / WorkItem / StageRun 状态机，依赖调度，人工审批，错误恢复，事件版本 | 用户凭据、假造供应商事件 |
| Context Compiler | 从任务简报/项目索引/选中文件/前置产物生成结构化 HandoffBundle，预算预检和去重 | 默认拼接整个仓库或完整聊天 |
| Provider Adapters | 声明能力与官方执行方式，启动/观测/取消/导入可用事件；不支持则显式降级为人工交接 | 偷用订阅 OAuth、假定所有 CLI 可无人值守 |
| Workspace & Evidence | Git Worktree、文件/目录前后快照、Diff、测试回执、进程与模型事件、审计账本 | 将时间相关推断为模型作者 |

推荐统一的逻辑关系：

- Task 是根：指向 PlanRevision、WorkflowDefinition、WorkItem、ContextManifest 和 StageRun。
- StageRun 指向 AgentRun（若发生）、ProviderAdapter、ContextSnapshot、Workspace、Approval、ToolOperation 和 Artifact。
- Artifact 是稳定可引用的产物：代码变更集、测试结果、Markdown 计划、用户确认决策、文档摘要；可由内容哈希与版本号识别。
- 每条 Event 有 taskId、stageRunId、runId、workspaceId、source、evidenceLevel、timestamp、eventVersion；展示页不得创建自己的第二套状态真相。
- 工件不能因为更换模型而消失；失败后也不能覆盖先前经确认的结果。

逐步迁移，不应一次推倒已有 JSON 数据。迁移必须有备份、schema 版本和回退策略。

## 3. 一次任务如何从 Claude 交给 Codex（目标行为）

用户输入：为指定 Windows 项目增加一个功能。

1. AIWS 创建 Task，收集用户目标、验收条件与工作区，不调用模型。
2. **本地路由策略**判断任务是否适合轻量执行。能由单个 Codex/Claude 阶段完成，就不自动启动第二个模型。
3. 只有复杂任务/用户明确要求时，才建立 Claude 规划 → Codex 实施 → Claude 复核的 DAG。
4. Claude 完成阶段后，保存人工可见的方案和经确认的关键决策为 Artifact；如有结构化事件，导入真实用量证据。
5. Context Compiler 仅提取 Codex 所需的目标、已确认方案、少量有关文件引用和 Git 基线，构成 HandoffBundle。用户预览来源、估算用量和未包含内容。
6. Codex 在专属 Worktree 执行；AIWS 记录可观察的工具/文件/Git 变更，不强迫 Claude 再看一遍完整仓库。
7. 若测试通过且风险低，直接进入人工审查；如需要 Claude 复核，交给它的是补丁、测试摘要、风险与特定问题，而不是完整此前对话。
8. 用户在**同一个任务页面**看到当前计划、调用/Token 证据、文件结构前后对比和各阶段完成情况。

**切换模型 ≠ 新建任务 ≠ 清空上下文。** 但供应商内部隐藏状态/隐藏推理不能跨模型迁移；只有 AIWS 保存且获得许可的显式产物可以转交。

## 4. HandoffBundle：减少 Agent 之间重复消耗

最小交接合同建议包含以下字段（正式实现前需版本化）：

| 字段 | 目的 |
| --- | --- |
| taskId / stageRunId / handoffVersion | 稳定身份与可重放验证 |
| objective + acceptanceCriteria | 保证不丢失原始目标、完成标准 |
| constraints + approvals | 权限和范围，避免重新协商已确认要求 |
| contextRefs | 文件路径/哈希、摘录版本、先前决策和计划工件引用 |
| deltaSinceLastRun | 当前阶段真正新增的事实与修改 |
| upstreamArtifacts | 前置 Agent 输出的有限摘要、Diff 和测试结果 |
| expectedOutputs | 必须交回哪些可验证工件 |
| providerCapability + mode | 自动化是否官方支持，或仅能用户确认后交互运行 |
| budgetEstimate + duplicateFingerprint | 本地提示词预算与完全重复调用防护 |
| provenance | 每条信息来自用户、官方模型事件、工具回执还是推断 |

实践规则：

- 确定性路由器优先，不要每切换一次 Agent 都再找“协调模型”询问一次。
- 同一项目的静态约束只维护一个源文件/版本，不在每一阶段重复生成新摘要。
- 只引用变更相关路径，按需从 Git 读取；文件大纲、结构树、计划看板、Diff 一律本地运算。
- 同一上下文快照计算指纹；未改变的文件和决策无需重复全文附加。
- 上下文太长时先提示用户/缩小范围，而不是默认启动“摘要 Agent”多花一轮 Token。
- 每次执行后保留输入估算、官方可观测 Token（若有）、本地节省量、重复记录和不确定性。
- 对官方交互式 CLI 无法控制的内部多轮调用，不宣称硬预算限额；只能约束 AIWS 本地交接和获支持的执行路径。

## 5. Agent 路由不是“模型比价器”

优先根据任务能力与风险决定是否拆分阶段，而不是只看模型名字：

- 简单代码修补：一个适用 Agent → 本地测试 → 人工确认。
- 架构讨论：规划 Agent + 人工决策 → 必要时另开实施阶段。
- 大型多模块变更：规划、可并行实施（隔离 Worktree）、证据驱动复核；DAG 必须有依赖和合并门槛。
- 单个阶段失败：针对失败证据局部重试，而非重新启动整个 DAG。
- CLI 不具备被允许的自动非交互或会话恢复接口：保留人工交接，不绕过官方认证或伪造自动化。

UI 应清楚解释“为什么选这个 Agent”“这个阶段为什么需要下一次调用”“为什么可复用旧产物”，提供用户覆盖选择、取消和审批。

## 6. 用户界面：一条任务，四个同步视图

统一 Task Workspace（不是四个互不关联的 App）：

- **Plan**：计划的阶段、依赖、用户确认的决策、待办；Markdown 更新实时同步为计划展示，但不会自动改写已批准 DAG。
- **Run Graph**：Agent/工具/模型请求的分层树，含状态、来源、上下文、Token/缓存、用时；未观察到的模型请求明确未知。
- **Project Evolution**：大型目录结构对比、新增/删除/移动、文件 Diff 与 Git Commit；点击阶段高亮相关文件，点击文件反查阶段。
- **Context & Budget**：即将交给下个 Agent 的内容清单、来源、重复项、估算 Token、已观测 Token，支持人工精简与审批。

四视图共享 taskId、stageRunId、artifactId，用户在 Claude 与 Codex 间切换时维持任务、焦点和产物。只允许在源状态更新后重新计算投影，不凭聊天回答更新 Git 状态。

## 7. 当前实现与缺口（2026-11-20）

**已存在的基础：** AIWS 自有 WPF/React、Task 和 WorkflowStep、DAG 依赖校验、用户审批、隔离 Git Worktree、Git 结构变化证据、执行事件账本、计划中心、按需本地交接、V1.7.2 本地估算预算/重复提示预检。其 Windows CI 和真实 VM 验收状况应分别记录。

**距离目标尚缺：**
1. 任务级、版本化的 ContextManifest / ArtifactStore / HandoffBundle，而不是只取最近完成阶段的结果文本。
2. 真正的 ProviderCapability 契约和会话恢复映射；不能因切换模型就默认复制全部历史。
3. 独立可恢复的 Scheduler/Worker，区分交互式 CLI 和官方可支持的程序化执行模式；所有非幂等步骤具有审批和幂等保护。
4. Plan → WorkItem → StageRun → GitChange 的统一引用和因果证据，减少手动在不同页面中查找。
5. 端到端性能/Token 基准：在相同真实任务样例下统计实际调用次数、准备文本量、官方用量证据和交付质量，而非凭空宣称节省百分比。
6. Hyper-V VM 中的权限、CLI 生命周期、系统终端、升级恢复的真实验收。

## 8. 下一批实施顺序（本文件是设计，不是运行时代码）

**A. 先统一任务与上下文**：引入 SchemaVersion、TaskContext、ArtifactRef、PlanRevision、StageRun，提供从旧任务 JSON 安全升级的兼容视图。

**B. 再接可解释路由与交接**：LocalTaskRouter + ContextCompiler + ProviderCapability，先在本地预览和人工确认路径完成端到端测试；不依赖任何额外协调模型。

**C. 补执行与证据**：稳定 Run/Process 事件、Worktree 变更和 Provider 官方结构化事件映射，故障后保持审批与幂等性。

**D. 最后自动编排**：只在合法、可支持的 provider 模式下执行 DAG 自动调度；否则使用同一 UI 中的受控手工交接，不能为演示而制造假的自动调用。

这四项属于 AIWS 下一阶段优先序列，不应牺牲原定 Windows 权限 Broker 的安全门槛。

## 9. 功能验收条件

- 一个项目任务可从 Claude 阶段换到 Codex 阶段，再返回 Claude，用户不必重建任务或重新录入已确认约束。
- 相同文件、相同任务指令的交接能预警重复文本；简单任务默认不会触发多次模型调用。
- 路由与上下文预览在离线状态可使用，UI 展示不发模型请求。
- 一处 Plan 状态变化关联 DAG、事件时间线和 Git 证据，老任务兼容且可追溯。
- 切换 Agent 不应把上游工具私有的不可见调用显示成已发生事件。
- 多 Worktree 任务并发的写入隔离、失败恢复、重复审批和取消能通过自动测试与 Windows VM 验收。
- 有固定对照任务衡量 token/上下文开销与实际质量；没有真实用量时，指标标注未知。
- 上游 UI/执行代码迁移遵守各自许可证和来源标注，保留每次修改的 docs/routine 日志。

**判断完成的标准：** 用户管理的是一个持续的任务，而不是一组需要自己人工搬运上下文的 Agent 聊天窗口。
