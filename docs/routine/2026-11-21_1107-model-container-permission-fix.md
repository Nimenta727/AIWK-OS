# 2026-11-21 11:07 — Repair actual Qwen inference container permissions after first CI failure

## 已确认根因
- 实际 GitHub workflow 44850313856 已成功编译固定版本 llama.cpp 并下载且通过 SHA256 校验的 Qwen3.5-2B Q4_K_M GGUF，证明源权重与引擎准备步骤真实执行。
- 首次 networkless non-root Docker 测试在 python3 打开 /opt/aiws/inference_smoke.py 时遇到 Errno 13 Permission denied；**模型并未开始推理，不得误标记真实推理成功。**
## 修改
- os/model/ci/Dockerfile 显式创建可遍历的 /opt/aiws 0755 目录，测试脚本权限改为 0644（模型文件仍为 readonly），容器仍为非 root 且禁网络/禁权限提升。
- .github/workflows/aiws-real-model.yml 增加执行测试前的非 root stat 诊断，直接暴露文件权限和目录遍历能力，随后执行真实 CPU 推理和隔离 QEMU guest 流水线。
## 后续
等待本次新流水线实际执行且得到 llama-server 真实健康、中文 JSON 提议和 RSS/延迟数据；继续修复任何模型或 ABI 兼容性问题。OS/UEFI A/B 也须真实 CI 成功。
