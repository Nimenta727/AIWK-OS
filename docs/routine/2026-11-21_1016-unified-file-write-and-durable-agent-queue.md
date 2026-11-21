# 2026-11-21 10:16 — Unify file editing and code read-only jobs through persistent guest DAG

## 主要修复
- 临时 /api/v1/jobs 原本还允许 file.replace 直接写文件，无审批且任务不持久，违反“统一 Agent”。现 EXPOSED 仅保留只读操作，直接写入返回 HTTP 400。
- GuestFiles.tsx 的手动修改从 /jobs 迁入 /tasks：提交后必须进入持久 DAG “写入待审核”状态，由用户单独批准，再显式执行；OsWorkbench.tsx 文件页完成后切到持久 DAG 页面。
- 生产环境里的传统只读 /jobs 也在 Agent systemd 独立服务中创建单阶段持久任务、派发，并将 SQLite stage 状态转换回原前端 Job 展示格式；`Controller.recent/job` 从持久库恢复，工作台 UI 重启不丢失结果。嵌入测试模式的只读 job 仍用原临时测试工作线程。
- os/verify/test_workbench.py 检验直接写入被拒绝、客体写入需要审批、SHA 旧版冲突失败与任务结果保存。

## 变更文件
os/runtime/aiws_workbench.py；desktop/AIWorkstation.Frontend/src/os/GuestFiles.tsx；OsWorkbench.tsx；os/verify/test_workbench.py；本 routine。
## 下一步
等待 Python/Windows/React 和 QEMU 真正 GUI 验收；检查 agent 用户服务重启恢复及文件编辑 UI 的完整审批点击；完善模型实际量化推理基线和内核启动 A/B 实验。
