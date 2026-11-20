# 2026-11-21 02:12 — Guest-only offline LoRA recipe with explicit resource consent

## 代码
- 新增 os/model/training/train_lora.py：默认仅 dry-run 检查数据，只有在显式 --train-in-guest 和 --ack-large-guest-memory-cost 双确认且验证 AIWS VM guest 标记、非 root、非 host mount、客体本地模型权重存在后才加载训练依赖。
- 实验性 SFT+LoRA 通过本地 Transformers/TRL/PEFT/Datasets 建立，只从 guest 的本地 base checkpoint 读取，不访问模型云端，不上传日志，不请求 GPU passthrough；训练输出存入 guest 用户目录。配置 LoRA rank=8、epoch 1–3，仅用于 benchmark，不代表已训练。
- 新增 os/verify/test_model_training_guard.py：验证默认仅 dry-run、环境防护标记和离线训练限制。
- 变更文件：os/model/training/train_lora.py，os/verify/test_model_training_guard.py，本 routine。

## 验证
真正 2B 训练未执行，无用户许可的训练语料或权重不可声称模型训练成功。CPU 上 2B LoRA 可能占用远大于 3–5GB 内存；3–5GB 预算仅用于推理场景。提交后 CI 运行默认 dry-run 静态检查；真正的 LoRA/QLoRA 训练必须在不访问用户主机的独立 AIWS guest 内进行，且先准备足够资源和版本兼容的依赖。

## 后续
先评测量化原版模型，然后扩大授权的训练/独立评测语料，验证模型运行、缓存与故障恢复、Windows 与 Linux 统一 DAG 语义、NixOS ISO/工作台界面可见可交互；若 LoRA 未改善效果则回退原版。
