# 2026-11-21 09:34 — Wire UI controller to independent systemd durable guest Agent

## 修改
- Debian Workbench 用户服务 Requires/After aiws-agent.service；客体启动工作台将先启动独立系统服务，保持系统服务、DAG、内核候选调度与浏览器 UI 进程生命周期解耦。
- os/runtime/aiws_workbench.py 生产模式强制使用同一用户私有 AF_UNIX socket 代理，不再自己开第二个 SQLite Controller；模型计划也走 daemon 内再验证并记审计。Agent 不可用时拒绝提供生产任务而不是降级不受审计执行。为不影响现有跨平台纯单元测试保留非 singleton 的 embedded-test 模式。
- 打包新增 aiws_agent_service.py / aiws_agent_client.py，并赋权限启动脚本。
- 新增 os/verify/test_agent_service.py，在 Linux 用私有 socket 实测任务保存/派发、模型提案待审核、禁止 direct service restart 和非法 host 工具。Windows 无 SO_PEERCRED 时跳过 Unix 专项。
## 验证/下一步
需经过 GitHub Python/Windows、实际 Debian ISO+QEMU、GUI 文件和内核候选审批测试；当前不保证通过。下一步统一旧的 /jobs 任务执行路径，完善 systemd 心跳/资源指标，生产模型 GGUF 的真实推理及独立 bootloader A/B 内核恢复。
