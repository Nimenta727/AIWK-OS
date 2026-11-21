# 2026-11-21 20:00 — 阶段 3：模型工具分级、多步计划、本机只读信息工具

## 用户约束（澄清）
小模型只在本地离线工作，不联网、不下载；只管理下载信息、读取进度，并可读取系统/本机网络状态。

## 改动
- `aiws_toolplane.py`：新增 `system.info`、`network.status`（仅读 /proc、/sys、/etc/resolv.conf，不开套接字）、`download.list`、`download.progress`；`READ_TOOLS`/`FILE_WRITE_TOOLS` 单一来源。
- `aiws_tasks / aiws_permission_broker / aiws_agent_service / aiws_workbench`：改为导入单一来源清单。
- `aiws_local_model.py`：读/写分级（`grade`、`requiresApproval`）；`MODEL_WRITE_TOOLS`；多步计划 `validate_any`（≤8 步）；`canonical`；`stages_from_proposal`（控制器计算指纹，拒绝过期/缺失源）；提示词更新（离线、不可下载、不可写内容）。
- `aiws_agent_service.py`：`task.model` 独立重验原始形态并建带指纹的阶段。
- `aiws_workbench.py`：`model_plan` 支持计划；前导只读阶段自动执行；上下文包含文件夹名。
- 前端 `GuestTaskStudio.tsx`：计划预览、写阶段参数显示、“批准并运行”、文案更新。
- 测试：`test_stage3.py`（18 项）、`test_agent_service.py` +2；`test_workbench` 一项改为接受自动执行。文档：`AIWS_NATIVE_AI_PLAN.md`。

## 发现并修复的缺陷
生产（Agent/IPC）路径的模型计划此前必失败：Workbench 传入 `validate()` 的输出（含 requiresReview 等字段），Agent 再 `validate()` 因字段不符而拒绝。已改为传 canonical 形态，并有回归测试。

## 验证
- Python：`unittest discover -s os/verify` 145 项通过，重复 3 次稳定（含自动执行线程的竞态检查）。
- 前端：`tsc --noEmit`、`npm test` 45 项、`vite build` 通过。
- 真实浏览器 + 本机回环 mock 模型：读步骤自动完成；写步骤批准前磁盘无变化；逐步“批准并运行”后 `downloads/a.iso` 移到 `isos/`，未完成的 `.part` 未被触碰；无页面错误。
- **未验证**：真实 2B 模型的工具选择/多步计划质量（训练集仍仅 18 条、评测集 26 条，且不含写工具/计划样本）；QEMU 客户机内的整体 GUI；`IPAddressDeny` 在用户级 systemd 下的实际生效（仅静态断言）。

## 下一步
1. 扩充训练/评测数据：写工具、多步计划、拒绝（联网/下载/永久删除/写内容）样本；`validate_dataset.py` 支持计划形态；LoRA 与独立评测门禁。
2. 阶段 4：模型路由（规则层→本地模型→官方 CLI，用户确认后升级；路由决策入 DAG 审计）。
3. 审计级“拒绝/放弃”状态；QEMU GUI 流程测试。
