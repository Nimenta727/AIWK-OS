# 2026-11-21 · 训练/评测数据集 v3（集成工具）

## 做了什么
- `generate_dataset_v3.py`：v2 逐字复制 + 新样本。新工具：`app.launch`（写，审批）、`doc.text`、`tools.list`、`ext.rg/jq/gitlog/sqlite`；新拒绝类：未登记程序、“打开终端并执行命令/用浏览器打开网址”、通过外部工具修改。
- 产物：`synthetic_intents_v3.jsonl`（train 882、dev 122）、`os/model/ci/heldout_v3.jsonl`（372 = v2 的 242 + 新增 130）。v2 文件字节不变（`--check` 两个生成器都通过）。
- train/dev/held 模板与词汇互不相交（有测试）；`validate_dataset.py` 现在对 v1/v2/v3 三份 held-out 做精确 + 近重复检查，通过。
- 规划器：`app.launch` 加入 `MODEL_WRITE_TOOLS`（永远是待批准阶段）；`LocalPlanner._check_external` 加语义限制；系统提示词加 4 句（长度受测试限制）。
- schema：`app.launch.id` 精确枚举（来自注册表），gitlog count / jq filter / sqlite query 用不含 `\b` 的 pattern；schema 只允许比验证器更窄，已测试。大小 16 KB（网关上限 20 KB）。
- 训练/评测默认数据集切到 v3；`guest_inference_smoke.py`、`build.sh`、`aiws-real-model.yml` 增加 v3 的**只报告**评测（`AIWS_GUEST_MODEL_BENCHMARK_V3`）。

## 验证
- Python 438 项通过；新增 `test_model_dataset_v3`（11 项：文件与生成器一致且 v2 未变、每个新工具的样本量与中英均衡、留出集是合法的发布集、独立性、组划分、所有启动目标都是登记程序、`app.launch` 恒为需审批的写、越界提议被拒、提示词内容与长度、Oracle 满分 / “什么都启动”的坏模型被发布门禁拒绝、路由器回归）。
- 路由器对留出集新增部分**只看了一次**：合法请求 98/98 本地；32 条拒绝类里 11 条禁止外送。看完后**没有改任何路由规则**，因此这个数字不被污染。

## 已知问题 / 未验证
- 没有用 v3 训练任何真实模型，没有真实推理基线；模板合成数据多样性有限。
- jq 改写 / sqlite 删表 / git commit·push / 打开未登记程序：规则层不禁止外送（云端构建器在授权内本来就能做）；本地模型拒绝为最终结论。若你希望这些也禁止外送，需要改规则并重新评估（会污染本次留出数字）。
- `$defs`/`pattern` 能否被真实 llama-server 的语法转换接受仍未验证（失败会回退普通 JSON 模式）。

## 下一步
1. 在真实客户机跑 QEMU 评测，拿到 v3 的第一份基线（只报告）。
2. 有基线后决定是否训练 LoRA（v3 数据），并观察“打开终端并执行命令”被误判成 `app.launch` 的比例。
3. MCP 客户端接入（沿用同样的分类与审批）。
