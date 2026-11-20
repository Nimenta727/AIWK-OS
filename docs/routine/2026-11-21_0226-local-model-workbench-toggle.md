# 2026-11-21 02:26 — Guest-only model enable/disable from AIWS workbench

## 功能
- 将本地模型从仅靠启动环境变量开关扩展成客户机可管理的状态：React AIWS 本地助手页面显示是否存在 guest GGUF 文件、仅限 CPU、已配置/在线状态，提供启用/关闭按钮。
- 受控服务 POST /api/v1/model/enable 与 disable 需要 Host/Origin/CSRF，Controller 先验证真实专用 guest VM、普通用户、权重必须位于客户机个人模型目录且无共享挂载，才运行固定的 systemctl --user enable/disable --now aiws-local-model.service。没有动态命令、主机 API 或模型自主控制。
- 状态标记在 guest ~/.config/aiws/local-model-enabled 中私有持久化，禁止符号链接。Debian user unit 提供 [Install] 但**镜像默认不启用**，需要用户在工作台内明确点击且已装权重。
- 影响文件：os/runtime/aiws_local_model.py、os/runtime/aiws_workbench.py、os/debian/config/includes.chroot/etc/systemd/user/aiws-local-model.service、desktop/AIWorkstation.Frontend/src/os/GuestTaskStudio.tsx、本 routine。

## 限制和验证
CI 需验证 Python/React 构建。模型权重尚未实际装载，用户没有导入权重时按钮禁用；推理/CPU 占用/显存/LoRA 结果均未实测。systemctl 固定服务操作只在 guest 中，不能触及宿主机；Hypervisor 安全仍需独立审计。

## 下一步
供应经过许可/哈希验收的客体模型权重；验证 guest CPU 基线、内存与质量评测，按需要再做真实 LoRA；持续任务 DAG 与 NixOS 适配、真实 GUI 长期测试。
