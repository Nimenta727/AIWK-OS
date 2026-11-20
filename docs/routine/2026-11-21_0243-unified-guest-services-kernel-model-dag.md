# 2026-11-21 02:43 — Unified guest system/kernel operations and durable model-planned DAG

## 本次落地
- 将 aiws_guest_ops 的 service.inspect/service.restart、kernel.inspect/stage/verify/recovery_plan/abandon 加入原有 Linux GuestTaskStore 工具白名单和 SQLite DAG 审批逻辑。每个阶段必须经过严格的工具参数 schema 验证，service.restart、kernel.stage、kernel.abandon 标记为 guest-write 并需明确批准后才能 dispatch。
- os/runtime/aiws_workbench.py Controller 接入同一 guest_op 执行路径，并向 React 能力列表暴露工具 schema；添加 GET /api/v1/guest/services、GET /api/v1/guest/kernel（仅在真实 VM 中允许），模型意图 POST /api/v1/model/plan 现在保存**未执行**的只读单阶段任务和 model.proposed 哈希审计事件，用户仍需手动 dispatch。
- 模型提议不会自动获得管理服务、内核或 root 权限；只有 read-only 工具允许由小模型建议。
- Debian ISO 打包新增 aiws_guest_ops.py；修复操作测试在 Windows 上以 mock 界限运行，不依赖真实 guest 或 host 特殊目录；platform.release 代替 os.uname，使跨平台静态测试兼容。
- 测试增加已审计服务 DAG 的审批限制、无 guest marker 时系统服务/kernel GET 拒绝、模型计划持久化和禁止把提示原文记录到审计。

## 文件
os/runtime/aiws_guest_ops.py、os/runtime/aiws_tasks.py、os/runtime/aiws_workbench.py、os/verify/test_guest_ops.py、os/verify/test_tasks.py、os/verify/test_workbench.py、os/debian/build.sh、本 routine。

## 验证/限制
需 CI 完成后才认定集成通过。持久 DAG 目前是单进程串行工具执行器，尚未迁移 Windows 完整的多 Agent DAG/交互协议；本地 2B GGUF 还未实际加载。Kernel 只支持候选阶段/哈希验证/撤销与恢复预案，不支持真实内核安装、bootloader、A/B 槽切换。Guest 根权限和宿主 VM 隔离的安全仍需独立审核。

## 下一步
增强任务重启/失败幂等，消除旧任务非持久队列；把系统服务和候选内核可视化接入工作台；增加可验证的内核 A/B 恢复实验环境和离线小模型真实推理与评测。
