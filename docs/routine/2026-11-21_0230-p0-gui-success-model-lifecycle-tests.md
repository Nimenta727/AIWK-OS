# 2026-11-21 02:30 — P0 AIWS Shell actual GUI success; local inference lifecycle denial tests

## 真实验收
- GitHub Actions run 44787989404 三个作业全部通过，Debian ISO 构建和 QEMU 内核直接启动后，LightDM 进入专用 AIWS Xsession、Chromium Kiosk 可见。
- guest Selenium 验证 React 真实 DOM 渲染、AI 文件结构点击及读取、创建/调度/执行持久 DAG 和本地模型关闭状态，串口出现 AIWS_GUI_BROWSER_PASS 和 AIWS_BOOT_SMOKE_PASS ... gui=clicked；1280x800 framebuffer 实际显示 AIWS OS 工作台。
- 这完成 P0 GUI smoke，不等于原生 ISO 固件引导、中文输入法/音频、长期稳定性和全量任务功能全部验收。

## 本次代码与文档
- aiws_workbench.py 将模型启停的 PermissionError 明确映射为 HTTP 403，防止在非 VM/主机上意外调用 systemctl 逻辑。
- OS HTTP 测试增加：没有真实 guest marker 时启用/关闭模型均拒绝，缺少 CSRF 也拒绝。
- Debian 可选模型 user unit 限定 MemoryMax=5G、CPUQuota=200%、TasksMax=80，仅 guest loopback IP；这是 CPU/内存限制而非显存实测。
- 更新 docs/AIWS_LOCAL_MODEL.md、docs/AIWS_OS_PRIORITY_GATES.md、README.md 和 docs/routine 索引。
- 修改文件：os/runtime/aiws_workbench.py, os/verify/test_workbench.py, os/debian/config/includes.chroot/etc/systemd/user/aiws-local-model.service, docs/AIWS_LOCAL_MODEL.md, docs/AIWS_OS_PRIORITY_GATES.md, README.md, docs/routine/README.md 和本 routine。

## 下一步
- 真实 GGUF 权重的客户机内许可/哈希供应、端到端推理、延迟/资源/意图质量基线与授权数据 LoRA 对照；**当前没有已训练模型**。
- P0 Linux 任务/DAG 与 Windows 所有协议语义对齐和持久恢复升级，P1 NixOS 真正 ISO build/boot，guest-only 权限与回滚。
- 更完整的 UI 体验测试、原生固件 ISO 启动与主机零控制安全验收。
