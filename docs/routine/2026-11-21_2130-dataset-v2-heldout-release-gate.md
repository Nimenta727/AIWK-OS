# 2026-11-21 21:30 — 数据集 v2、锁定评测集 v2、独立性检查与发布门槛

## 改动
- 新增 `generate_dataset.py`（确定性、合成、双语）→ `synthetic_intents_v2.jsonl`（664 train + 80 dev）与 `ci/heldout_v2.jsonl`（242 例，越权 100）。
- `validate_dataset.py`：支持多步计划（并经真实 stage builder 校验）；新增 held-out 独立性检查（精确 + 近重复）与统计摘要。
- `guest_benchmark.py`：`write`/`plan` 案例、`byKind`/`byLanguage`、`release=True` 的发布门槛。
- `train_lora.py`/`evaluate.py`：提示词同源、canonical 目标、训练前强制独立性检查、v2 默认。
- `aiws_local_model.system_prompt()` 抽出为单一函数。
- CI：真实 QEMU 额外对 v2 只报告；工作流上传 v2 回执；`build.sh` 在 CI-only 镜像中放入 v2 评测集。
- 文档：微调标准新增第 6 节。

## 发现并修复的问题
- v1 训练集与 v1 held-out 存在近重复（`读取 README.md` vs `读取 README.md 说明`）。
- v2 越权训练样本借用了 v1 held-out 的句子。
- 生成器的计划校验抓到“把文件移进它自己所在的文件夹”的无效计划，已在取样阶段排除。

## 验证
`python3 -m unittest discover -s os/verify -p 'test_*.py'`：154 项通过（新增 `test_model_dataset_v2.py` 9 项：生成可复现、规模与均衡、训练目标安全、独立性、组划分词汇不相交、泄漏检测、发布门槛对 oracle/不拒绝/颠倒计划/丢参数模型的反应、训练与推理同提示词）。
**未验证**：真实 2B 模型在 v1/v2 上的任何指标；LoRA 实际训练未运行。

## 下一步
阶段 4：模型路由；之后在真实客体上跑 v2 取得基线，再决定门禁。
