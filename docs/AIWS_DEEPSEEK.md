# 云端模型：直接接 DeepSeek API（自带智能体循环）

**English summary.** Instead of wrapping vendor CLIs, the cloud model is reached through the DeepSeek HTTP API by our own agent loop (`aiws_cloud_agent.py`), run as a separate process under the existing builder supervisor. Because we execute every tool call, approvals are synchronous (nothing runs before you answer), plans are structured and reviewable, sub-agents are first-class, and token/cache numbers come straight from the API. The key lives in a private file and is passed to the runner through a pipe. **Nothing here has been run against the live DeepSeek service**; the API facts come from the official docs and are tested against a synthetic fake server that reproduces the documented rules.

## 1. 为什么自己写循环
| | 包装官方 CLI | 自己的循环（本方案） |
| --- | --- | --- |
| 批准 | 只能事后发现再暂停 | **同步**：工具由我们执行，你点头之前不会运行 |
| 计划 | 从文字里猜 | 模型调用 `plan_propose`，结构化；风险由平台按工具类别算 |
| 子智能体 | 靠解析 CLI 输出 | `agent_spawn` 原生产生 node/parent/model/ctx，树页直接可用 |
| token | 依赖 CLI 字段 | API 的 `usage` 原样上报，含缓存命中数 |
| 依赖 | 要装并登录 CLI | 只需 API 密钥 |

## 2. 结构
```
你 → 观察台「构建」→ 授权令牌（工具、预算、时间、需批准的类别、是否先批计划）
        └→ 监督器 ──启动──→ aiws_cloud_agent.py（独立进程，可用专用用户 + 域名白名单代理）
              ▲  stdin: 任务+密钥（管道）/ 批准结果          │ stdout: 事件、计划、批准请求、最终答案
              └───────────────────────────────────────────────┘
runner ──HTTPS──→ api.deepseek.com（唯一放行的域名）
runner 的工具：工具平面（限定在项目文件夹内）+ plan_propose / plan_update / agent_spawn + **build_run（受限的编译/测试/运行，见第 8 节）**；**没有 shell**
```
- 事件进事件库（与其他来源同一套严格模式，不含消息正文）；计划进计划库；最终答案进结果库（事件库不存正文）。
- 预算、墙钟时间、调用次数由 runner 自己限制，**监督器再独立执行一次**（任何一方失效另一方兜底）。

## 3. 按官方文档做的设计决定（来源见第 7 节）
- **端点/认证**：`POST https://api.deepseek.com/chat/completions`，`Authorization: Bearer <key>`；只接受这个主机（测试时才允许回环）。
- **模型名是配置，不写死逻辑**：文档当前列出 `deepseek-flash`、`deepseek-v4-pro`；旧名 `deepseek-chat`/`deepseek-reasoner` 按更新日志已于 2026-07-24 停用，所以**没有放进白名单**。模型表会变，换名只改 `aiws_deepseek.MODELS`（客户端也提供 `list_models()`）。
- **思考模式**：默认开启。带 `tools` 时，**所有历史 assistant 消息的 `reasoning_content` 必须原样传回，否则 400**：循环保存完整 assistant 消息；假服务器实现了同样的 400，所以漏传会在测试里失败。思考模式下 `tool_choice` 只用 auto/none。
- **工具参数是字符串**：可能不是合法 JSON、也可能因 `finish_reason: length` 被截断：每个 `tool_call_id` 都会得到一条错误回复（否则下一次请求会被拒），模型据此重发。
- **缓存**：系统提示是固定前缀（无时间戳）、工具按名字排序，利于 DeepSeek 默认开启的前缀缓存；`usage` 里的 `prompt_cache_hit_tokens` 作为 `cacheRead` 上报，**不估算**。
- **上下文压缩**：超过阈值后只把**旧的工具结果**换成占位说明；assistant 消息不动（因 reasoning 规则）。
- **重试**：仅 408/429/500/503 和网络错误，指数退避加抖动，次数有上限，遵守 `Retry-After`（上限 60 秒）；400/401/402/422 不重试。402（余额不足）有专门的提示。
- **不流式**：先用非流式（文档说明非流式连接会收到空行保活，推理 10 分钟内未开始才会断开）。界面因此没有“逐字显示”，这是已知取舍。

## 4. 安全
- **密钥**：只存在 `~/.config/aiws/deepseek.key`（权限 600，普通文件、非链接、属于本人、≤512 字节）；不进工作区、任务数据、事件库、日志、命令行、环境变量。监督器读取后通过管道交给 runner；界面只能看到“已配置/来源/末 4 位”，可保存或清除，无法读回。
- **runner 没有 shell，也没有联网工具**：只有工具平面的文件/搜索工具（路径被限制在项目文件夹内：`..`、绝对路径、符号链接、`.git` 都被拒）和第 8 节的 `build_run`（固定命令，默认关闭）。网络出口只有它自己的模型调用，经域名白名单代理时只放行 `api.deepseek.com`。
- **提示注入**：系统提示声明工具返回内容是数据而不是指令；真正的防线是上面的“没有 shell + 路径限制 + 同步批准”。
- **授权令牌**：`deepseek` 令牌只能列出 runner 自带的工具名（无模式、无通配）；`network`/`shell`/`outside-project` 批准仍然不可关闭；写入类可选“每次先问”，删除类（进回收站）每次都要你批准。

## 5. 怎么用
1. 在「构建」页的 DeepSeek 密钥面板保存密钥（或设环境变量 `DEEPSEEK_API_KEY` 供开发使用）。
2. 在 `~/.config/aiws/builder.json` 写 `{"enabled": true}`。要联网，需构建通道隔离（`isolation.mode="user"` + 防火墙 + 域名白名单代理，见 `os/builder/README.md`）；默认**不隔离且 runner 不继承代理环境变量**，没有网络的客户机里调用会以“无法连接”结束。
3. 选 DeepSeek、模型、是否思考、推理强度、允许的操作，写任务，授权并开始。计划会出现在「计划审核」，你批准后它才动手；每个删除/（可选的）写入会在「总览」等你。

## 6. 没做 / 没验证（如实）
- **从未对真实服务发过请求**：参数名（`thinking`、`reasoning_effort`、`user_id` 等）、400 的触发条件、`usage` 字段，都来自官方文档的抓取摘要；抓取工具对部分页面有截断/摘要，已在日志里标注。第一次真实运行请观察：是否 400（尤其 reasoning_content）、`usage` 是否带缓存字段、模型名是否被接受。
- **没有 shell**；编译/测试/运行靠 `build_run`（第 8 节），默认关闭，要专用用户隔离才开放。
- **不流式**；**不计费**（不用价目表估算金额；只显示 API 上报的 token）；**一次只跑一个运行**；子智能体顺序执行、不能再派子智能体、最多 8 个。
- 本地小模型还没接入这条链路：下一步用它压缩工具结果、把长答案摘要给你看、预审明显越界的任务。
- 真机上的网络路径（专用用户、防火墙、代理放行 `api.deepseek.com`）未验证。

## 8. 编译、测试、运行：`build_run`（不是 shell）
模型只能选「语言 + 动作 + 一个目标」，命令是**固定模板**：没有自由参数、没有管道、没有 `sh -c`。

| 语言 | 动作 check / build / test / run 实际执行的命令（节选） |
| --- | --- |
| C / C++ | `cc -std=c17 …` / `c++ -std=c++20 …`；文件夹里有 `CMakeLists.txt` 用 cmake+ctest，有 `Makefile` 用 make |
| Go | `go vet / build / test / run`（`GOPROXY=off`、`GOTOOLCHAIN=local`） |
| Python | `py_compile` / `compileall`；测试用 pytest（有就用）否则 `unittest`；运行 `python3 文件` |
| Rust | 有 `Cargo.toml` 用 `cargo … --offline`，否则 `rustc` 单文件（含 `--test`） |
| Java | 有 `pom.xml` 用 `mvn -o`，否则 `javac` + `java -cp`（自动识别 `package`） |
| JavaScript | `node --check` / `node 文件` / `node --test` 或 `npm test --offline` |
| C# | 有 `dotnet` 用 `dotnet build/test/run`，否则用 Mono 的 `mcs` + `mono`；**镜像里目前两者都没有** |

- **每次先问你**（可在构建页取消）：批准框显示完整命令，拒绝则程序不会运行。
- **目标校验**：相对路径、在项目内、无符号链接、不以 `-` 开头、扩展名要对；多余参数一律拒绝。
- **沙箱**：最小环境变量（不继承任何密钥/令牌）、cwd=项目、独立进程组、超时后整组杀掉（含孙进程）、CPU/文件大小限制、stdin 关闭、输出写临时文件并只回传头尾各 4000 字符。
- **离线**：不给这些进程网络，cargo/go/npm/pip 也被告知不要联网，所以**依赖必须事先备好**（Maven 需要预先填充好的本地仓库）。
- **产物在可执行的临时目录**（`AIWS_BUILD_SCRATCH`，默认 `/var/tmp`），不在 `noexec` 的工作盘上，运行结束即删除；项目里不留 `target/`、`__pycache__`、`CMake*` 等（测试验证过）。
- **只在构建通道有专用用户隔离时才开放**（`isolation.mode="user"`）。原因：模型写的程序会以运行器的身份运行，没有隔离就等于以**你自己的权限**运行（能读你的文件和密钥文件）。确实想在不隔离的机器上用，需在 `builder.json` 写 `"execWithoutIsolation": true`——这是明确标注的危险开关，默认关。
- 子智能体拿不到 `build_run`。

## 7. 来源
- DeepSeek API 文档：https://api-docs.deepseek.com/ （聊天补全、思考模式 /guides/thinking_mode、工具调用 /guides/tool_calls、缓存 /guides/kv_cache、错误码 /quick_start/error_codes、限速 /quick_start/rate_limit、模型与价格 /quick_start/pricing）
- 同类开源项目（只看设计，未使用其代码）：Reasonix（缓存优先、前缀稳定）https://api-docs.deepseek.com/quick_start/agent_integrations/reasonix ；DeepSeekCode（带确定性模拟服务器的 Go 智能体）https://pkg.go.dev/github.com/amemiya02/deepseekcode ；社区文章对“工具调用 JSON 被截断、写进思考文本”的观察（二手，作为风险提示）https://dev.to/esengine/how-a-deepseek-only-agent-framework-hit-85-prefix-cache-rate-and-saved-93-vs-claude-5c9g
- DeepSeek Harness 桌面端（社区项目，MIT）：https://github.com/anywhere-labs/dsh-desktop 。它把官方 `@deepseek-ai/dsh` 当子进程运行，插件是 Cordis（Node）模块，插件接口在上游仓库里，**本项目没有读到**，因此没有直接复用其插件；对应的功能已在前面做成内建模块。
