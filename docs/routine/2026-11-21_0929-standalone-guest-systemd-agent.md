# 2026-11-21 09:29 — Persistent Linux systemd guest Agent with same-UID IPC

## 本次代码
新增 os/runtime/aiws_agent_service.py 与 aiws_agent_client.py：专用普通用户的持久 DAG service 进程，控制任务审批与客户机系统服务及内核候选执行。工作台将通过私有 AF_UNIX socket 访问，不暴露 TCP/host API，核验 SO_PEERCRED 同用户并限制请求字节数。服务所有写操作先进入 SQLite DAG 并要求审批，普通直接 IPC 仅允许只读 guest 工具。
新增 Debian systemd --user aiws-agent.service、aiws-agent 启动脚本，启用资源配额和自动重启。
## 当前验收
这次仅引入独立服务与 socket 客户端基础，下一提交才真正将工作台指向该服务，并更新 Debian 镜像打包、用户单元依赖和集成测试。不能宣称此刻后台 Agent 已在真实客体运行。后续仍需要整套 QEMU GUI 与实际模型/内核 boot 恢复验收。
