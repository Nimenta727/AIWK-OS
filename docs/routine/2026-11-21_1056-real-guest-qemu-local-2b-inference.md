# 2026-11-21 10:56 — Actual Qwen3.5-2B QEMU Linux guest inference acceptance

## 新增真实客户机模型验证
- os/model/ci/guest_inference_smoke.py：只有一次性 ISO 特殊标记的客体、普通 user、客体虚拟机 guard 才允许手动启动 aiws-local-model.service，等待真实 localhost llama.cpp 服务健康，使用本地 Qwen3.5-2B Q4 发出中文只读工作区工具意图，校验 JSON 工具结构且不执行模型建议。输出服务准备时长、首次建议时延、云端调用 0、CPU-only 标志。结束时停止客体服务。
- Debian build.sh 可选 `AIWS_OS_MODEL_GUEST_CI_TEST=1` 才将客体验收代码和标记写入 ISO。aiws-boot-smoke 在标记存在时必须真实执行此项并输出 AIWS_GUEST_MODEL_INFERENCE_PASS，否则整个 GUI/Agent 模型验收失败。默认 ISO 不含标记、不执行此测试或自动启用模型。
- .github/workflows/aiws-real-model.yml 在实际权重+llama.cpp CPU 基准后新增构建带真实模型的 Debian ISO（从受控文件/许可证/SHA256 变量打包），真正 QEMU 客体启动，模拟图形点击和内核候选审批后进行离线本地模型推理，并上传串口证据，不上传权重。

## 验证状态
该提交引发较重的端到端 CI，必须在 ISO 构建、QEMU Agent/GUI、真实模型 SHA 与输出均实际通过后才能称已完成模型真实部署和测试。出于资源限制、第三方量化兼容性，可能失败；不能隐去失败。内核 UEFI A/B 和原版 LoRA 微调仍单独跟踪。
## 下一步
核对 CI 超时、OOM、模型运行错误并修复；得出首 token/整句响应延迟和 Linux guest 实际 CPU/内存占用，扩展独立 50–100 个授权意图 eval，再决定是否微调及发行。
