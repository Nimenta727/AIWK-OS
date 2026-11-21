# 2026-11-21 10:09 — Real quantized Qwen3.5-2B CPU inference benchmark CI

## 本次实现
- 新增 os/model/ci/Dockerfile + inference_smoke.py 和 .github/workflows/aiws-real-model.yml。自动在 GitHub 运行器构建固定提交 29b52d398b294509746ec0a3f28948a3107c0213 的 llama.cpp CPU 服务，下载真实 SoAIHQ/Qwen3.5-2B-GGUF Q4_K_M 文件（Apache-2.0 源许可声明），严格比对公布 SHA-256 a8b50de00b780c0f3c16f07cb041a1ecd678b6e22fd8cde91e57fe4b5031523b。
- 只有完整哈希校验通过才在非 root、无网络、cap-drop ALL、资源限制容器中启动真实模型，通过 OpenAI-compatible API 发出合成中文工具计划测试，记录真实服务加载耗时、首次推理延迟、RSS、模型 JSON 输出是否符合工具规则以及 token usage。绝不自动执行模型建议。
- 该测试**不是**真实 AIWS QEMU 客户机系统上的模型运行；需要再把通过验证的模型/推理引擎集成到 guest 模型服务并在真实 VM 内验收。GGUF 不上传到仓库或 CI artifact。
## 后续
首先确认此真实模型测试是否完整通过（可能受外部下载及 llama.cpp 构建兼容性影响）；随后建立可下载/可安装的 guest-only 离线包、验证模型版本回退、内存和全套评测，最后上正式客户机。真实内核 B→A firmware 实验也在 CI 中独立进行。
