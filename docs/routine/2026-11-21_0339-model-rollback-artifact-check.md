# 2026-11-21 03:39 — Prevent activation/rollback of corrupted archived GGUF model

## 修复
- 模型版本切换前不再仅凭版本目录的文件存在就创建激活链接；现在先完整计算版本文件 SHA-256，与期望精确 digest 不匹配立即拒绝，原本正在使用的模型版本保持不变。
- 新增跨平台离线模型测试：安装两个合成 GGUF 版本，篡改旧版本后尝试回滚必须拒绝，并确认当前版本仍然通过校验。
- 修改 os/runtime/aiws_model_registry.py、os/verify/test_model_registry.py、本 routine。
## 验证与下一步
需 Python/Windows CI 测试；本测试数据仅用于版本完整性，不是真实模型权重或推理质量测试。下一步客体真实 Qwen 2B 权重许可/哈希、服务基线、故障注入和正式 A/B kernel boot。
