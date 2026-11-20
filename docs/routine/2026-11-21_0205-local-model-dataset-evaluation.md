# 2026-11-21 02:05 — Local model dataset validation and offline benchmark

## 新增
- os/model/training/synthetic_intents.jsonl：16 条明确标为 synthetic 的中英文 AIWS 文件、代码及拒绝宿主操作的意图样例，10 train / 6 eval。没有用户私有文件或模型权重。
- validate_dataset.py：严格校验 train/eval schema、数据来源、重复样本和 tool allowlist。默认不执行推理、不调用任何网络。
- evaluate.py：默认静态校验；仅明确 --live 且通过 dedicated guest 检测才向 guest 内 127.0.0.1 本地模型发请求，报告结构化有效率、工具与参数准确率。不执行模型建议的任何工具。
- os/verify/test_local_model_dataset.py：CI 验证样本安全边界与 split。

## 文件
os/model/training/synthetic_intents.jsonl、validate_dataset.py、evaluate.py、os/verify/test_local_model_dataset.py、本 routine。

## 验证状态
提交后应由 OS static CI 验证。本数据集是用于质量门槛示范的少量合成样本，**不能作为已获得用户授权的真实训练数据，也不能证明模型微调有效**。无 GGUF 权重、无 LoRA 训练完成记录，GPU 3–5GB 未实测。下一步是 guest-only 实际推理基线、大规模独立 eval 数据、用户授权语料和在客体内的 opt-in PEFT 训练。
