# 2026-11-21 02:20 — Integrate AIWS Shell/DAG/local model into project documentation

## 修改
- 根 README 更新产品现状：AIWS kiosk Shell 取代 Debian 实验桌面默认入口，guest SQLite 持久任务/DAG/审批/审计与离线小模型建议层已提交；是否通过实际虚拟机 GUI 验收待看 CI；模型权重与训练未完成。
- docs/README 添加小模型文档入口；docs/AIWS_OS_PRIORITY_GATES.md 补充四项核心目标的最新实现与未验收条件；docs/routine/README.md 索引近期每次 GitHub 变更。
- 本次改动路径：README.md、docs/README.md、docs/AIWS_OS_PRIORITY_GATES.md、docs/routine/README.md、本 routine。

## 验证与限制
现有后端/DAG/模型数据/安全相关 OS 静态测试已通过；新的专用 AIWS GUI 的实机 QEMU 流水线仍在运行，不能提前说 P0 GUI 验收完成。NixOS 真正 ISO 构建与 VM 启动仍没有实证。模型训练和真实推理尚未执行。

## 下一步
拿到并解读新的 QEMU 串口与 framebuffer + Selenium 证据，修复失败；继续迁移 Windows 任务协议，完善 NixOS AIWS Shell；在客户机内验证小模型量化、实际显存/CPU/时延、授权样本评测及微调对照。宿主机不进入任何 Agent API 的权限范围。
