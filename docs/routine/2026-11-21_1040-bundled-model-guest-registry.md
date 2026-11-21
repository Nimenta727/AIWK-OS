# 2026-11-21 10:40 — Guest-only bundled model registry with strict checksum

## 变更
- aiws_model_registry.py 增加 --import-bundled 模式；运行中专用 Linux guest（非宿主）只能导入 ISO 内 /usr/local/share/aiws/model-preload 的 root-owned 非符号链接文件。首先读取固定 manifest 模型 ID、许可审核标志和 SHA256，再完整校验 GGUF 内容/大小；复制到 guest 普通用户 0700 版本库、写入独立 registry 并支持原版回滚。若已存在不同 model 注册版本，不静默覆盖。
- test_model_registry.py 使用合成 GGUF 进行 manifest 导入、重复导入以及篡改拒绝测试；**不等于真实模型推理**。
- 文件：os/runtime/aiws_model_registry.py、os/verify/test_model_registry.py、本 routine。
## 下一步
添加受来源哈希约束的 Debian ISO 可选打包与首次 boot 导入；CI 完成实际下载/构建真实 Qwen3.5-2B GGUF 后才能在专用 VM 使用。仍需客体本地推理和 CPU/内存实测；保持默认模型关闭。
