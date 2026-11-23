# 2026-11-22 14:46 — 本地模型改为 9B，专用 Agent 接口（循环、技能、插件、路由、读日志）

## 背景
用户要求：只保留 7B 级模型、删除 2B 权重；针对这个模型设计专用 agent 接口，模仿成熟 agent（技能、插件），结合报告《Claude、DeepSeek 与 Codex 客户端机制和云端效率》，按我们的系统深度制作模型接入方式，"把模型接入完全"，有补充自己做。

## 做了什么
- **模型**：产品模型固定为 Qwen3.5-9B（Q4_K_M，5.68 GB，Apache-2.0，sha256 `03b74727…b7e8`）。7B 级里我测的是这个 9B（同家族最接近的一档），**没有测 Qwen3-8B 或其他厂家**。2B 权重已删除（只存在于我的临时目录，仓库里本来没有）。登记表只认 9B；CI 流水线冒烟用的小模型只在 CI 专用标记存在时才放行；权重大小上限 4 → 12 GiB；启动脚本加内存守卫（权重 + 5 GiB，不够就明确拒绝，退出码 75）、上下文/线程可配置；服务单元 `MemoryMax` 12G；发布流程改成 9B 并如实写明内存需求。
- **客户端** `aiws_llm.py`：OpenAI 兼容、只对环回地址说话；结构化输出按 `json_schema` → `json_object+schema` → `json_object` → 无 降级，按错误文字点名要剥离的字段；本地再校验并给模型一次精确修复；流式时记录真实首字时间；令牌/缓存/用时只照搬服务端报告；前缀被改写时指出是第几条消息。配套 `aiws_jsonschema.py`（带错误路径的校验器）。
- **循环** `aiws_local_agent.py`：线程/回合/条目，追加式 JSONL 落盘，下一步请求由落盘条目逐字节重建；动作 `call`/`calls`/`skill`/`propose`/`final`/`refuse`，schema 按本轮可见工具现场生成；只读工具自动执行，改动只能提案（同一个 `LocalPlanner` 裁判，批准后才执行），提案记录"读过哪些文件"；工具输出裁剪、确定性压缩、有界并行只读调用、崩溃恢复；四个时间点和缓存/前缀/压缩度量；一次一个回合。
- **技能/插件** `aiws_skills.py`、`aiws_plugins.py`、`os/plugins/`：Agent Skills 格式的 `SKILL.md`（渐进披露），Claude Code 目录约定的插件，**只取文字**（技能、命令、只会拒绝的守卫、只会升档的路由提示），钩子/MCP/脚本/`bin` 一律列出并不运行；系统插件哈希固定，用户插件默认禁用、启用需带上用户看过的目录哈希、任何改动自动失效。两个第一方插件：`aiws-log-tools`、`aiws-secret-guard`。
- **路由** `aiws_route.py`：local / flash / pro 三档，只在任务开头选；本地 9B 按有判定顺序的提示词判档，规则只升不降，给中英文原因，可一键改，改动被计数。
- **读日志**：工具平面新增只读工具 `log.digest`（相同模板合并、保留首次行号和次数、原文引用）和 `log.lines`；Broker/Agent 服务/任务引擎自动覆盖（都从 `READ_TOOLS` 派生）。
- **模型门**：放宽到 agent 需要的程度（见"真实验证发现的问题"）。
- **工作台**：`aiws_assistant.py` + 端点 `/assistant/{status,threads,thread,plugins,turn,route,route/override,plugins/enable,plugins/disable}`；前端新页面"本地助手"（对话、实时步骤、被裁剪的观察、提案和"去审核"、路由卡片、斜杠命令、插件启停对话框含"不会被使用的部分"）；原来的旧页面保留为"本地模型开关"。
- **工具/评测/数据**：`router_bench.py`、`route_eval.py`、`agent_eval.py`；数据 `router_v1/v2_heldout/v3_fresh.jsonl`；原始结果存档。

## 涉及文件
新增：`os/runtime/{aiws_llm,aiws_jsonschema,aiws_local_agent,aiws_skills,aiws_plugins,aiws_route,aiws_logdigest,aiws_assistant}.py`；`os/plugins/**`；`os/model/bench/{route_eval,agent_eval}.py`；`os/model/ci/router_v3_fresh.jsonl`；`os/verify/test_{llm,logdigest,skills_plugins,local_agent,route,assistant,agent_through_gate}.py`、`fixtures/fake_llm.py`；`workbench/src/app/Assistant.tsx`；`docs/AIWS_LOCAL_AGENT.md`；`os/model/bench/results/2026-11-22/*`。
修改：`os/runtime/{aiws_model_registry,aiws_model_gate,aiws_model_router,aiws_model_schema,aiws_toolplane,aiws_workbench}.py`、`MODULES`；`os/debian/build.sh`、启动脚本（两份）、服务单元；两条工作流；`os/verify/fixtures/fake_llama.py` 与 5 个既有测试；`workbench/src/app/{App.tsx,app.css}`；`docs/{AIWS_LOCAL_MODEL,README,THIRD_PARTY}.md`、`os/README.md`、`CHANGELOG.md`。

## 验证
- Python 全量与前端（`tsc`、`vite build`、45 项单元）结果见文末"最终测试结果"。
- **真实 9B + 真实 `llama-server`（自己用 PyPI 源码包里的 llama.cpp a956a85 编出来，参数与镜像启动脚本一致）**：
  - 路由：留出集 v2 上 2B 90% / 9B 96.7%；**全新集 v3（结果出来前固定）9B 45/45**，规则未触发。
  - 读日志：12 份合成日志 9B 12/12、2B 8/12、grep 6/12。
  - agent 端到端 9 个场景 **9/9，修复 0 次，失败调用 0 次**（读日志中英文、读文件、列目录、移动提案、拒绝、提示词注入、取密钥、两次读取）。
  - 整栈：真实工作台 HTTP 服务 + 真实 9B：读一份 C 编译日志，引用的行号正是标准答案 [485, 486]；移动请求落成计划审核区里一条 `file.move`（中风险、需批准），文件未动，观察台有记录。
  - `llama-server` 实测事实：`json_schema` 原生支持；`timings` 字段齐全；探测拿到 ctx；混合架构的前缀缓存在追加式对话上有效（610 个 token 命中 508，预填 3.0 s 对 11.5 s）；常驻内存 10.2–10.7 GB；CPU 生成 3.3–4.2 token/s、预填约 44 token/s。
- 前端：真实浏览器（Playwright，接口用夹具模拟）中英文截图人工看过，无页面错误、无横向滚动。

## 真实验证发现并修掉的问题
1. 模型门会拒绝 agent 的请求（角色、消息数、`chat_template_kwargs`、流式、超时）。
2. `log.lines` 的行号被模型填成整条日志文本。
3. 工具检索对中文几乎检索不到工具；释义式说法找不到 `file.read`。
4. **旧的"禁止类别"把程序员日常词当成危险请求并强制留在本地**（10/10 条普通请求命中）；`root cause`、"安全审计"误报。这些规则现在只提示、不改档位。
5. 守卫路径归一化 `lstrip("./")` 把 `.env` 变成 `env`，点文件绕过守卫。
6. 启动内存守卫估计偏乐观。
7. 真实 `llama_cpp.server`（Python）不按 oneOf 约束，模型输出过 `call`/`calls` 混用形状 → 读取端放宽、执行端严格。
8. 一个已有的偶发失败测试（`test_model_channel` 超大请求）。

## 已知问题 / 局限
- **没有在真机、没有在显卡上跑过**；CPU 上一个回合要几分钟。显卡延迟、其他 7–9B 模型、多槽并发都没测。
- 评测题和日志是合成的，由写规则的同一个人写；路由 45/60/90 条、日志 12 条、端到端 9 个场景，单次、温度 0：说明"能工作"，不说明"多可靠"。
- `llama-server` 是在本环境自己编的，与镜像里固定的提交（`29b52d39…`）可能不同；镜像那个版本的 `json_schema`/`timings`/前缀缓存行为未验证。
- **真实的模型门没有和真实 9B 一起跑过**（门拒绝以 root 运行，我没有绕过）。门用脚本化子进程做了集成测试，9B 用 `llama-server` 直连验证。
- 规划器（一次性）的 held-out 门槛尚未在 9B 上重跑。
- 标签由我定；v1/v2 的数字不能当泛化证据（提示词和规则看过它们）。
- 技能/插件的命令只在本地助手里展开，云端构建页不读。
- 路由结果只是建议：构建页尚未自动采用它（需要手动选择模型和思考开关）。

## 下一步
1. 在你的显卡上用同一份评测复跑（`route_eval.py`、`agent_eval.py`），补显卡延迟，并加测 Qwen3-8B。
2. 用镜像里固定的 llama.cpp 提交和真实的模型门（非 root 用户）再跑一遍 `agent_eval.py`。
3. 把路由结果接到构建页（一键采用 flash/pro 与思考开关），并让 `被你改过的比例` 成为上线门槛。
4. 在 9B 上重跑规划器 held-out 门槛。
5. 扩充路由集到 200 条并请另一个人复核标签；加入真实日志（多行堆栈、超长行）。
6. 考虑把 `calls`（并行读取）在真实使用里的收益测出来：它省的是 CPU 上的慢往返，但会增加模型出错的形状。

## 最终测试结果
- Python 全量 **913 项通过**（2 项为既有跳过）；前端 `tsc` 通过、`vite build` 通过、45 项单元测试通过。
