# 2026-11-21 11:35 — Diagnose real llama.cpp crash before health readiness

## 客观结果
在首次 non-root Docker 文件权限修复之后，真实测试 44851179237 已成功构建固定版本 llama.cpp、验证 Qwen3.5-2B Q4 模型哈希、创建隔离容器并确认 /opt/aiws 路径权限，但 llama-server 在健康检查前直接退出；因为先前把输出只写进容器 /tmp/aiws-llama.log 而容器销毁，无法判断根本错误。此时**仍无真实成功推理记录**。
## 本次修改
- os/model/ci/inference_smoke.py 仅在推理失败时输出本地 llama-server 标准输出日志最后 14k 字符，避免泄漏模型权重或上传大型日志。成功时仍只输出真实延迟、模型及响应数据指标。
- aiws-real-model.yml 在非 root 受限容器内运行 ldd，打印动态依赖与可能缺失的共享库，确保至少能定位 ABI/动态库问题后再启动真实 2B 推理。
- 修改文件：os/model/ci/inference_smoke.py、.github/workflows/aiws-real-model.yml、本 routine。
## 下一步
根据下一次真实 stderr 修复 loader 参数/动态库/模型兼容性，完成 CPU 和 QEMU 实际推理门槛。UEFI OVMF 故障回退另行独立 CI 验收，不能将未通过称完成。
