# 2026-11-21 10:49 — Load verified bundled model in place without copying weights to RAM overlay

## 修改
- 对模型内置 ISO 增加 `aiws_model_registry.py --verify-bundled`：先检查 guest VM/普通用户、root-owned 构建来源、非 symlink、许可标记、完整 SHA256 和 GGUF magic，但只返回校验信息，不写入用户文件或启动服务。
- aiws-local-model shell 在存在内置 GGUF 的 guest ISO 中先执行 verify-bundled，然后直接从 ISO 的只读根文件系统加载模型，避免在 Live ISO 的 tmpfs/overlay 中多次复制约 1.5 GB 权重造成 OOM。没有内置模型时继续使用私有版本库 verify。
- Workbench 启用 UI 接受可信的内置模型但始终要主动点击；无模型默认禁用。状态 API 区分模型文件存在与推理服务在线。打开 Chromium 时不再强制复制多 GB 的权重。
- 测试新增 `verify_only` 不建立 registry，之后实际导入仍可用。
## 文件
os/runtime/aiws_model_registry.py、os/runtime/aiws_local_model.py、os/runtime/aiws_workbench.py、os/debian/config/includes.chroot/usr/local/bin/aiws-local-model、os/debian/config/includes.chroot/usr/local/bin/aiws-open-workbench、os/verify/test_model_registry.py、本 routine。
## 下一步
真正模型 Q4 CPU 运行与资源指标 CI；打包 ISO 从已验证模型/二进制构建，在真实 QEMU 内手动启用模型并验收。需解析独立 UEFI A/B、Agent 与 GUI CI，不能把配置完成当真实推理通过。
