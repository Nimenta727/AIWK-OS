# AIWS V1.7.2 — Token-efficient Agent architecture / 节省上下文的执行基座

> 2026-11-20. **Status: implementation, Windows CI pending until verified.**
> These controls apply to **AIWS-authored, local handoff drafts**. They do not enforce provider billing caps, subscription limits, or total internal usage of a separately running Claude Code/Codex interactive CLI.

## 目标与可证实边界

用户希望 AIWS 的模型调用、DAG、多 Agent 交接、计划展示、Git/文件可视化尽量不额外消耗 Token：

- 打开、展开、筛选工作流/文件/计划/事件树始终使用本地数据，不调用模型。
- 只有用户明确批准、启动官方 CLI 后，才可能触发提供方模型；AIWS 复制交接提示词而不会自动发送。
- 阶段准备、Token 预估、重复检测、预算检查都是 .NET 本地确定性操作，未连接外部接口。
- **外部 CLI 内部的对话历史、系统指令、工具输出、MCP 工具 schema、缓存和模型请求不可由 AIWS 直接计量或限制。** 未导入官方结构化证据时实际量仍是 unknown。

## 参考成熟平台，采用的设计及限制

| 上游 | 可核验设计 | AIWS 的取舍 |
| --- | --- | --- |
| T3 Code [portable handoffs](https://github.com/pingdotgg/t3code/blob/main/docs/user/portable-handoffs.md) | 按预算筛选近期对话，保留原始用户请求，不强行缩短当前输入；可引用省略的上下文 | 交接最多纳入最近两项完成结果、每项最多 1200 字符；用户阶段指令不做静默截断，超限需明确处理；不移植 T3 服务或复制 T3 的账号会话 |
| OpenCode [compaction](https://opencode.ai/docs/compaction) | 接近上下文阈值时压缩，预留剩余容量；摘要本身也会消耗 Token | AIWS 当前只做**零模型调用**的交接节流和本地提示；不额外请求一个总结模型，尤其避免给每个阶段都做总结 |
| Codex [agent loop](https://openai.com/index/unrolling-the-codex-agent-loop/) | 重视稳定前缀与 prompt caching，控制会破坏缓存的工具/schema 配置变更，长会话才触发压缩 | AIWS 固定执行规则、避免无意义地重发完整项目；但不假设能控制官方 CLI 内部缓存策略 |
| Claude Code [usage limits and context](https://support.claude.com/en/articles/14552983-models-usage-and-limits-in-claude-code) | 新任务可清空无关历史；必要时 compact；引用具体文件路径而非粘贴整个文件 | 默认轻量模板仅一个模型阶段；上下文交接使用阶段目标与有限结果；计划/文件树显示不自动发送源码 |

## 实际修改（V1.7.2）

1. **轻量模板优先**：新任务默认 `lean`（Codex 实施 + 人工复核），不默认运行“Claude 分析 → Codex 实施 → Claude 审查”的三模型流程。复杂任务可手动选择多 Agent 或并行 DAG，仍逐次批准。
2. **交接预算**：每个任务保存“提醒阈值”和“本地拦截阈值”，默认分别约 **2500** 与 **6000** 的估算 Token；配置有效域为 `500 ≤ warning < stop ≤ 50000`。
3. **启动前预检**：检查真实即将复制的本地 handoff 文本，返回预估 Token、原始字符、缩减字符数、是否重复、是否触发提醒/拦截。前端只看摘要，不被动传出 prompt。
4. **预算闸门下沉 .NET Core**：超限时 `LaunchWithGitAsync` 和 `Launch` 在剪贴板/进程启动前拒绝；不是仅在 React 中禁用按钮。调整预算由控制层验证、保存到 JSON 并记录元数据事件。
5. **重复启动阻断**：相同阶段提示词指纹未变时，核心默认拒绝；只有经过原生窗口额外用户确认后，才可尝试启动。指纹用于本地比较，不保存完整提示词到事件账本。
6. **正常提示明确披露**：启动前显示实际评估值、配置门槛以及 CLI 内部用量未知。警告只表示草稿可能较长，不宣称节省了确定百分比。
7. **数据兼容**：新增的 WorkTask 预算字段具有旧 JSON 缺省值，TaskRepository 在加载和写入前执行校验；已有 V1.7.1 任务可继续打开。

## Token 预算不是实际计量

`HandoffBuilder` 使用字符启发式预估，输入语言、分词器、工具声明、缓存和官方 CLI 的系统上下文会使真实 Token 与预估值不同。**即使本地草稿小于拦截阈值，也不能保证实际使用量不超过该阈值。** 软硬门槛名称仅指 AIWS 本地文本预检，不表示官方硬限额或账单限额。

如果某模型提供受支持的用量/预算控制协议，后续可实现“官方 provider budget”；在该功能上线前绝不以 UI 估算代替真实指标。用户可调整 AIWS 阈值，以免正常复杂任务被本地配置误阻断。

## Test & acceptance

- 原有 Python：`python -m pytest -q`。
- 前端：`cd desktop/AIWorkstation.Frontend && npm test && npm run build`。
- .NET 核心 Smoke：预算配置、旧 JSON 兼容、重复指纹、超长指令、不复制不启动、单 Agent 模板和持久化。
- Windows EXE：GitHub Actions `Native Windows Desktop EXE` 需通过 React TypeScript、WPF/.NET 10、核心 Smoke 和独立打包检查。
- Hyper-V VM 实验仍需用户测试：切换任务、原生重复提示词确认、复制失败、真正 CLI 退出后重试、中文输入与 UI 布局。

## 后续设计（必须分清“可控”和“不可控”）

- 建立官方受支持的 Codex app-server/ACP 事件适配器，只有返回 token 用量的原始事件可标记 measured；保持原始认证方式与安全权限。
- 使用“上下文 manifest”（文件路径、Git SHA、引用行、摘要来源）替代大文本粘贴；只在工具明确读取时取原文件段落。不能仅靠路径声明保证模型不会自行重复读取。
- 对大工具输出进行本地过滤：保留退出码、有限 stderr 与关键失败行；完整日志单独本地归档，打开全文由用户决定。
- 将缓存命中/实际用量/重复任务比率作为**观测指标**，用固定任务基准对比完成质量与用量，避免因过度压缩而增加返工成本。
- 自动压缩只有在有可信剩余上下文/阈值信息且用户允许时才启动；否则宁可明确请求确认，不额外花一轮模型 Token 做泛化总结。
