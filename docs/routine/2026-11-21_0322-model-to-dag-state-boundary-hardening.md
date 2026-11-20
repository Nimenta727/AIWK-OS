# 2026-11-21 03:22 — Direct local-model proposal to pending DAG and guest state mount hardening

## 改动
- 本地小模型界面新增“生成并保存待审核任务”：调用 POST /api/v1/model/plan，直接创建包含只读工具、模型名、提示 SHA 与提案 SHA 的持久化 DAG；仍须用户独立点击调度，模型没有系统服务、内核、文件写入的自主权限。
- 生产模式 Controller 使用 XDG_STATE_HOME 时，必须位于真实客体用户 HOME 内，拒绝外部路径/符号链接并经过 protect_guest_workspace 审计，防止用户级任务数据库意外落入 guest-host 共享挂载。单元测试仍使用隔离虚拟状态目录。
- GuestTaskStore.verify_audit 检查 seq 事件是否连续与任务存在但全无审计的情况，在简单审计行删除后阻止任务继续执行；增加覆盖测试。
- 修改：GuestTaskStudio.tsx、aiws_workbench.py、aiws_tasks.py、os/verify/test_tasks.py、本 routine。

## 验证/限制
需要新 CI React/Windows 与 Python/guest ISO 验证。该模型请求仍然需要已经在 guest 启用且完成真实权重 SHA 审核的本地小模型。当前没有发行 GGUF 权重与已训练 LoRA，不能声称模型现已能实时推理。审计哈希链没有对抗 guest-root 全量重写的保护，下一阶段需进行独立签名/追加式外部证据。
## 下一步
客户机真实权重运行与评测；恢复 DAG/服务/内核候选自动化回归；NixOS 真实 ISO 与 A/B kernel boot 恢复前置条件及权限 broker。
