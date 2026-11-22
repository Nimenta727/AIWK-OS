# Local model pipeline / 本地小模型工程

本目录包含**可选**离线小模型运行器、独立评测和训练配方。存在代码或数据集不代表模型已训练、已发布或通过真实客户机验收。

| 位置 | 用途 |
| --- | --- |
| `aiws-local-model.sh` | 客户机模型服务启动 |
| `ci/guest_benchmark.py` | 工具选择、参数、明确拒绝、延迟、内存门禁 |
| `ci/heldout_v1.jsonl` | 独立双语小规模 smoke 数据集（不作训练） |
| `ci/guest_inference_smoke.py` | 真实 QEMU 客户机模型服务与基准 |
| `ci/Dockerfile*` | 构建/检查环境 |
| `training/train_lora.py` | LoRA 训练配方 |
| `training/validate_dataset.py` | 数据校验 |
| `training/evaluate.py` | 离线训练/评估辅助 |
| `training/synthetic_intents.jsonl` | 合成训练样本 |
| `bench/router_bench.py` | 路由（local/flash/pro）与读日志的离线评测，含规则基线；需要 `llama-cpp-python` |
| `ci/router_v1.jsonl`、`ci/router_v2_heldout.jsonl` | 路由评测集（后者是未参与调提示词的留出集） |
| `bench/results/` | 评测原始结果存档（结论见 `docs/routine/` 对应日志） |

**质量原则：** 模型只能提出结构化建议或明确拒绝；不能跳过 Agent、Broker 和用户审批执行工具。smoke 数据集规模不够支撑生产发布；正式发布应按 [微调与独立评测规范](../../docs/AIWS_MODEL_FINETUNING_STANDARD.md) 使用更大的严格隔离 held-out 集、模型/adapter 哈希、P95/RSS 和回滚证据。

[OS 工程](../README.md) · [模型集成](../../docs/AIWS_LOCAL_MODEL.md)
