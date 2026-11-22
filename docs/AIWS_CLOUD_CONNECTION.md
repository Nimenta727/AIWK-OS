# 云端模型怎么接：官方插件调研与连接方案（2026-11-22）

> **2026-11-22 更新：决定先不适配 CLI，改为直接用 DeepSeek API 自带智能体循环，见 [AIWS_DEEPSEEK.md](AIWS_DEEPSEEK.md)。** 本文保留为 CLI 路线的调研记录；其中“同步批准、计划、子智能体”的需求在新方案里是原生满足的。

**English summary.** Claude Code and Codex share three open conventions we should build on instead of inventing our own: `SKILL.md` skills, MCP servers, and `AGENTS.md`/`CLAUDE.md` guidance. Best connection: for **Claude Code**, keep the `stream-json` process and add a **PreToolUse hook that calls our local broker** (a synchronous gate: real prevention instead of detect-after) plus an **MCP server** exposing a curated read-only subset of our tools; for **Codex**, use **`codex app-server` over stdio** (it sends approval requests to us, streams plans, sub-agent items and token usage) with `codex exec --json` as fallback. The local model never approves anything; it routes, compresses context, summarises results and retrieves tools. Items marked ⚠ were **not verified against a real CLI**.

> 资料来源有两类：一手（官方文档页、官方仓库目录）和二手（博客、社区库）。每条结论后标了可信度；官方页面被截断或由工具摘要的部分单独标注。**没有一条经过真机运行验证。**

---

## 1. 官方插件：哪些能借

### 1.1 Claude Code（`anthropics/claude-plugins-official`，仓库 Apache-2.0；各插件许可需逐个看）
- 官方自己维护的 `plugins/` 目录有约 32 个插件（一手：目录列表）。形式：`.claude-plugin/plugin.json` + 可选 `skills/<名>/SKILL.md`、`commands/`、`agents/`、`.mcp.json`、`hooks/hooks.json`、LSP 声明。
- **和我们目标相关的**：
  | 插件 | 它做什么（官方描述） | 我们怎么借 |
  | --- | --- | --- |
  | `code-review` | 多智能体 PR 审查，带置信度打分 | 借思路：变更审查页可按“多视角 + 置信度”给出提示，而不是只列 diff |
  | `security-guidance` | 编辑时按模式预警，结束时审查 diff | 借思路：和我们的 PreToolUse 闸门同类，规则可参考 |
  | `hookify` | 从对话/规则生成 hook | 借思路：让用户用自然语言加“拦截规则”，本地模型生成、人审后写入闸门配置 |
  | `claude-md-management` | 维护 CLAUDE.md | 借思路：我们按项目生成 CLAUDE.md/AGENTS.md（见 §4） |
  | `session-report` | 读 `~/.claude/projects` 生成用量报告 | **有价值**：Claude 会话日志本身是 token 用量的第二来源，可与 `result.usage` 交叉核对 |
  | `feature-dev`、`skill-creator`、`plugin-dev`、`mcp-server-dev` | 工作流/开发辅助 | 可作为“可选安装”，不预装 |
  | `*-lsp`（pyright、typescript、gopls、rust-analyzer、clangd、jdtls、kotlin、lua、php、ruby、swift、csharp） | 语言服务器声明 | 语言服务器本体是独立开源程序，可由我们的代码理解层直接用，不必经过 CLI |
- **不建议默认装进构建通道**：插件是第三方代码，在 CLI 权限下运行；官方 README 自己写了“请先确认信任再安装”。如要用，放进授权范围、固定版本、记录哈希。
- 许可：仓库 Apache-2.0，可以借鉴/改写（保留 NOTICE）；**逐个插件的 LICENSE 我没有逐个核对**。

### 1.2 Codex（OpenAI）
- 一手（官方文档，已迁到 learn.chatgpt.com）：技能是 `SKILL.md`（`name`、`description` 头部 + 可选 `scripts/ references/ assets/`），仓库技能放 `.agents/skills`，全局放 `~/.agents/skills`；指导文件是 `AGENTS.md`；文档说“技能是编写格式，插件是安装分发单位”；技能依赖 MCP 时写在 `agents/openai.yaml`。
- 插件清单文件 `.codex-plugin/plugin.json`、`.mcp.json`、`.app.json`、市场文件 `.agents/plugins/marketplace.json`：**只来自二手资料**，官方页没写 ⚠。
- **没有查到 OpenAI 官方出品插件的清单**（只看到导航里有 “OpenAI Developers plugin”“Codex Security plugin”“Admin plugin” 的名字，没有读内容）。所以这一半“有哪些可借”**我无法回答**，需要你在 Codex 桌面端的插件页里看一眼并把名单发我。
- “桌面端”：二手资料称 Codex 应用与 ChatGPT 桌面应用在 2026-07 合并，单一来源 ⚠，不影响接入（我们接的是 CLI/app-server，不是桌面界面）。

### 1.3 结论：真正值得借的是“约定”，不是某几个插件
两家共用三件事：**SKILL.md 技能**、**MCP**、**AGENTS.md/CLAUDE.md**。因此：
1. 我们的 skill 改成 `skills/<名>/SKILL.md`（`name`、`description` 之外保留我们自己的 `keywords`、`requires` 字段，CLI 会忽略未知字段 ⚠）。**同一份技能同时给本地模型检索、给 Claude Code 和 Codex 使用**，不再是三套。
2. 我们的工具平面以 **MCP 服务**形式开放给两家 CLI（已有 `aiws_mcp.py`、`aiws-toolctl`）。
3. 每个项目目录生成 `CLAUDE.md` 与 `AGENTS.md`（内容相同，稳定前缀便于服务端缓存）。

---

## 2. 请求与返回：四条通道

```
你 ─自然语言→ 本地模型（路由、整理上下文）
                │
        ┌───────┴────────────────────────────┐
        ▼                                    ▼
  控制通道：监督器启动/观察/停止        上下文通道：CLAUDE.md/AGENTS.md + skills + 任务描述
        │                                    │
   Claude Code: stream-json 进程         （只含名称、摘要、错误片段，不含整文件）
   Codex: app-server (stdio JSON-RPC)
        │ 云端 CLI 要调用工具时
        ├──→ 闸门：PreToolUse hook → 本机 Broker（同步 allow/deny/ask）        [Claude]
        ├──→ 闸门：app-server 的 requestApproval 请求 → 我们回答            [Codex]
        └──→ 工具通道：MCP（aiws：只读子集 + 能力检索 + 记忆读取）→ 工具平面
        │
        ▼ 返回通道
  事件（parent/model/ctx/usage）→ 事件库 → 观察台 / 智能体树
  计划（TodoWrite / plan 项）→ 计划库 → 计划审核区
  结果与 diff → 本地模型做摘要 → 给你看；变更审查页看真实 diff
```

### 2.1 Claude Code
| 方式 | 说明 | 取舍 |
| --- | --- | --- |
| A. `claude -p --output-format stream-json --verbose`（现状） | 子进程、逐行 JSON | 零依赖；**只能事后发现**危险操作（我们靠 SIGSTOP 暂停，不是预防） |
| B. Agent SDK（`canUseTool` 回调） | 官方 SDK，进程内同步批准 | 预防性强；多一个依赖，版本漂移；**订阅账号能否这样程序化使用，条款曾多次变化，我无法确认** ⚠ |
| C. **PreToolUse hook**（`--settings` 指向我们的配置） | CLI 在每次工具调用前运行我们的命令，返回 `allow/deny/ask`；多个 hook 里只要有一个 `deny` 就拦截（一手：官方 hooks 文档的社区转述） | **推荐**：真正的预防，不依赖 SDK；hook 程序是我们自己的可信代码 |
| D. MCP（`--mcp-config`） | 把我们的工具暴露给云端 | 推荐，见 §2.3 |

**推荐 = A + C + D。** C 的要点：设置文件放在项目目录之外（CLI 里的 agent 改不到）；hook 把 `tool_name/tool_input/cwd` 交给本机 Broker 套用授权令牌的规则（工具白名单、项目目录、需批准的类别）；`ask` 对应你在观察台点批准。⚠ hook 的输入输出字段和 headless 下 `ask`/`defer` 的行为要用真实 CLI 验证。

### 2.2 Codex
| 方式 | 说明 | 取舍 |
| --- | --- | --- |
| A. `codex exec --json` | 一次性，输出 JSONL：`thread.started`、`turn.started/completed/failed`、`item.started/completed`、`error`；`turn.completed.usage` 含 `input_tokens`、`cached_input_tokens`、`output_tokens`、`reasoning_output_tokens`（一手） | 简单；事件粗，审批只能靠 `--sandbox`/`--ask-for-approval` 预设 |
| B. **`codex app-server`（stdio，JSON-RPC 2.0）** | 官方说它是驱动 VS Code 扩展等“富客户端”的接口：线程/回合/条目；`item/commandExecution/requestApproval`、`item/fileChange/requestApproval` 等**服务器发给客户端的审批请求**；`turn/plan/updated`（`{step,status}` 数组）；`collabToolCall` 条目（含 `senderThreadId`、`receiverThreadId`、`newThreadId`、`agentStatus`）对应子智能体；`thread/tokenUsage/updated` | **推荐**：审批是同步的，计划和子智能体是一等事件。注意：官方页面被截断，**整体稳定性没写**；WebSocket 传输明确是“实验、不支持”，所以只用 stdio |

沙箱/审批预设（一手）：`--sandbox read-only|workspace-write|danger-full-access`，`--ask-for-approval on-request|never`；`--yolo` 仅限隔离环境，**任何授权令牌都不放行**。

**推荐 = B（app-server over stdio）+ MCP，A 作为回退。**

### 2.3 工具通道：把本地能力开放给云端（MCP）
- 两家都支持 MCP，所以只做一套：把工具平面的**只读、受路径限制**的子集 + `capabilities.select`（能力检索）+ 记忆读取，作为 `aiws` MCP 服务给云端用。云端要“看工作区结构 / 搜索 / 读小文件 / 查系统状态”时，由本地离线完成，返回的是**短结果**，省云端 token。
- 暴露面刻意收窄：不暴露写工具和启动程序（写操作走云端 CLI 自己的、受授权约束的工具）；路径限制沿用现有规则；结果长度有上限；没有密钥。云端模型的输出本身不可信，MCP 服务要当作不可信输入处理。

### 2.4 本地模型在这条链路里做什么（以及不做什么）
做：①路由（现有）；②**整理上下文**：把任务压成“目标 + 文件名 + 错误片段”再交给云端；③**摘要返回**：云端长输出先在本地压成几句话给你看；④**能力检索**：只把 6 个左右的工具/skill 给模型；⑤**预审**：明显越界的请求在发往云端前就拒绝；⑥**把待批准事项翻成人话**（解释，不决定）。
不做：**不替你批准任何操作**；不读写云端凭据；不把整份转录发回云端。

---

## 3. 我没法确认的事（要真机验证）
1. Claude Code：hook 的真实输入字段、`--settings`/`--mcp-config` 在 `-p` 模式下的行为、`ask` 在无人值守时的结果；`parent_tool_use_id`、`task_*` 事件的真实形状（社区资料称默认只转发子智能体的 tool_use/tool_result，文字需额外开关 ⚠）。
2. Codex：app-server 的完整方法与通知清单（官方页被截断）、token 通知的字段名（页面没写）、是否稳定。
3. 两家订阅账号用于程序化调用的条款（曾多次变化）。
4. 官方 Codex 插件名单。

**请你跑的两条命令（把输出贴给我，我据此写适配器）**：
```
claude -p "list files and spawn one subagent to read README" --output-format stream-json --verbose > claude.jsonl
codex exec --json "list files in this folder" > codex.jsonl
```
若装了 Codex，再运行 `codex app-server --help`，确认子命令里有没有生成协议模式（schema）的选项，有的话把它导出的 schema 发来，这样适配器就不用猜字段。

## 4. 建议的实现顺序（需要你点头再开工）
1. **Claude 闸门**：`aiws_hook_gate.py`（PreToolUse → Broker），先用合成输入测，再用真机录制校对。
2. **MCP 开放**：整理 `aiws_mcp.py` 的“云端可见子集”，加 `capabilities.select`、记忆读取。
3. **Codex app-server 适配器**：JSON-RPC 客户端 + 审批回调 + `turn/plan/updated` → 计划库 + `collabToolCall` → 智能体树。
4. **skill 统一格式**（`skills/<名>/SKILL.md`）和**项目级 CLAUDE.md/AGENTS.md 生成**。
5. 把 `session-report` 的思路做成“会话日志交叉核对 token”。

## 5. 来源
- Anthropic 官方插件目录：https://github.com/anthropics/claude-plugins-official （目录列表为一手；`marketplace.json` 约 19 万字符，部分由抓取工具摘要，已标注）
- Claude Code 插件清单参考：https://code.claude.com/docs/en/plugins-reference
- Claude Code hooks：https://code.claude.com/docs/en/hooks ；hooks 与权限回调顺序：https://code.claude.com/docs/en/agent-sdk/hooks
- Codex app-server：https://developers.openai.com/codex/app-server （已迁至 https://learn.chatgpt.com/docs/app-server，部分内容被截断）
- Codex 非交互模式：https://learn.chatgpt.com/docs/non-interactive-mode ；自定义（skills/AGENTS.md）：https://learn.chatgpt.com/docs/customization/overview
- Codex 插件与市场（二手）：https://codex.danielvaughan.com/2026/04/11/codex-marketplace-plugin-distribution/
- Agent Client Protocol（编辑器与 agent 的通用协议，Zed 主导；我们暂不采用，仅作参考）：https://github.com/agentclientprotocol/agent-client-protocol
- 工具检索对小模型的影响：RAG-MCP https://arxiv.org/abs/2505.03275 ；AgentFlux https://arxiv.org/abs/2510.00229
