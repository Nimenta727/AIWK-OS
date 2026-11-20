# 2026-11-21 02:35 — 统一 Agent 的客户机服务与可撤销内核候选管线

## 本次改动
- 新增 os/runtime/aiws_guest_ops.py：GuestOperations 只向专用客户机普通用户提供固定名单的 systemd user service.inspect/service.restart，其中 restart 仅允许 aiws-local-model.service，且只有经过 DAG 审批才能执行。完整拒绝任意 service 名称、命令和 host 操作。
- 提供 kernel.inspect/stage/verify/recovery_plan/abandon。kernel.stage 只读取客户机 workspace 内带 SHA-256 前置条件、16 KiB 以下、白名单 CONFIG_ 项的 .fragment；快照与元数据在私有客户机目录并记录 SHA。verify 会检查候选版本完整性，abandon 撤销候选状态而保留源快照，recovery_plan 给出恢复前置条件。
- **刻意不支持内核安装、启动项修改、root、运行中模块更换或 VM 重启。** bootRecoveryReady=false，真正 A/B 内核恢复尚未建立，不能将 staging 撤销描述成系统内核回滚。
- 新增 os/verify/test_guest_ops.py，覆盖审批、固定 systemd 命令、候选完整性、篡改拒绝、拒绝未经标记的执行环境。
- 本次是模块与测试，尚未接入统一 HTTP/DAG，下一提交接入、验证。

## 影响文件
os/runtime/aiws_guest_ops.py；os/verify/test_guest_ops.py；本 routine。

## 验证与下一步
需 GitHub CI 验证。下一步将这些受限操作接入已有持久 DAG 的 schema、审批和审计，并将本地模型提案转成未执行的持久任务；再实现只读系统服务 UI、可审计 A/B boot 构建环境与恢复前置条件。模型不获 root 或宿主机能力。
