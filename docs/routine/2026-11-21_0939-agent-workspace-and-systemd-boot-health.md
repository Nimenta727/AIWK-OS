# 2026-11-21 09:39 — Fix systemd Agent environment and require its boot health

## 修复
- 新独立 Agent 的 systemd 用户进程不会继承工作台 shell 的 AIWS_WORKSPACE，导致 toolplane._workspace() 拒绝任务。现启动时强制把经过专用 guest/home/mount 校验的 workspace 路径写入 Agent 环境，再启动 socket。
- Workbench API 统一处理 AgentUnavailable/AgentError 的任务详情和审计请求，返回明确信息而非断开 HTTP；删除重复 except 分支。
- Debian 客体启动验收新增 systemctl --user is-active aiws-agent.service 及 /api/v1/health 中 agentIndependentService 的强约束。此后如果服务未真实运行，不得输出 AIWS_BOOT_SMOKE_PASS。
## 文件
os/runtime/aiws_agent_service.py、os/runtime/aiws_workbench.py、os/debian/config/includes.chroot/usr/local/bin/aiws-boot-smoke、本 routine。
## 下一步
持续运行 OS 静态、Python/Windows、Debian ISO+QEMU 真实 Selenium 验收，分析失败并修复。需要将旧的文件修改 /jobs 也迁入持久 DAG，真实离线模型运行、A/B kernel boot 尚未实现。
