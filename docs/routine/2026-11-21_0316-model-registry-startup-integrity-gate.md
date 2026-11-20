# 2026-11-21 03:16 — Require versioned signed-by-hash GGUF registry before guest model activation

## 修改
- 将 os/runtime/aiws_model_registry.py 打包入 Debian/ NixOS guest Python runtime；Debian 客体可选模型脚本 aiws-local-model 在调用 llama-server 前，必须在 guest 用户目录校验 registry.json 与 aiws-local.gguf 的精确 SHA-256；未安装、未注册或已篡改权重拒绝启动。
- 后端工作台模型启用 API 在真实 guest gate 通过后调用 GuestModelRegistry.verify，不仅检查文件存在，还要求版本快照、manifest 和当前权重一致。
- 模型 registry 自身修复文件打开后显式关闭；若 registry.json 已存在但损坏，拒绝绕过并覆盖。
- 本地模型没有默认下载权重，也不会与宿主文件、宿主 GPU、外部 API 或 Hypervisor 交互。

## 影响文件
os/runtime/aiws_model_registry.py、os/runtime/aiws_workbench.py、os/debian/config/includes.chroot/usr/local/bin/aiws-local-model、os/debian/build.sh、本 routine。

## 验证与下一步
需运行 Python/Windows 回归、Debian ISO 构建/启动。还没装载真实 Qwen3.5-2B GGUF、也未实测 token 速度、内存、GPU 占用或完成 LoRA 微调。后续在专用 guest 内经许可与 hash 审查导入真实模型，进行端到端推理、客体服务恢复和小模型策略评测。bootloader A/B 可恢复内核仍未完成。
