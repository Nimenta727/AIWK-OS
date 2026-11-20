# 2026-11-21 02:51 — Durable Agent audit and crash-recovery hardening

## 修改
- 为真实客户机 TaskStore 增加 Linux flock 控制器单例锁，避免重入的双控制器误将活动任务判作故障恢复。
- 增加 verify_audit 哈希链校验与 GET /api/v1/audit/verify；启动及关键任务状态迁移前 fail-closed 检查篡改。该校验不能防止掌握客体数据库完全写入权的主体重新计算哈希。
- SQLite task.created 审计条目改为仅保存阶段名称、依赖与参数 SHA-256，不重复存储可能包含隐私的文件内容。
- 客户机进程中断后，带副作用的 file.replace、service.restart、kernel.stage、kernel.abandon 均清除旧审批；要求再次审批才能重试。React 支持 interrupted 的重新审批。
- 新增 os/verify/test_tasks.py 的审批恢复、隐私与审计链篡改检查。

## 修改文件
os/runtime/aiws_tasks.py, os/runtime/aiws_workbench.py, os/verify/test_tasks.py, desktop/AIWorkstation.Frontend/src/os/GuestTaskStudio.tsx, 本 routine。

## 验证与下一步
CI 需实跑 Python/Windows、Native Windows 与 Debian ISO+QEMU 验收。多 Agent 并行调度、可靠 Linux 内核 A/B 启动回滚、guest-root 防篡改审计与真实 2B 权重仍未交付。下一步加强内核候选服务可视化、模型建议任务联动、长期故障恢复测试和 NixOS ISO。
