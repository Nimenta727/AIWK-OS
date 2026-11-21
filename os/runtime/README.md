# Linux guest runtime / 客户机运行时

此目录是 **Linux 客户机** 的 Python 服务实现，不是 Windows WPF 的替代构建入口。

| 模块 | 职责 |
| --- | --- |
| `aiws_workbench.py` | 客户机 localhost Web API、前端与 Agent 接口 |
| `aiws_agent_service.py` / `aiws_agent_client.py` | 独立 systemd 用户 Agent、UNIX IPC |
| `aiws_permission_broker.py` | 同 UID、fail-closed、私有 UNIX Socket 的策略服务 |
| `aiws_tasks.py` | SQLite DAG、审批、执行状态、审计 |
| `aiws_mcp.py` | 只读 MCP stdio 门面，经 Agent/Broker 转发 |
| `aiws_toolplane.py` | 工具实现和静态工具清单；不是安全沙箱 |
| `aiws_guest_ops.py` | 受限的客户机服务/内核候选操作 |
| `aiws_local_model.py` | 可选 GGUF/llama.cpp 建议及拒绝协议 |
| `aiws_windows_compat.py` | Windows 历史证据导入，不继承审批 |
| `aiws_guest_boundary.py` | 客户机路径/运行环境约束；不构成宿主隔离 |

**权限顺序：** Workbench → Agent → Broker → 持久化 running DAG 阶段 → 工具。对外 MCP 仅暴露只读操作。Broker 与 Agent 仍是同 UID，恶意同 UID 进程可能绕过：详见 [威胁模型](../../docs/AIWS_PERMISSION_BROKER.md)。

修改任何运行时模块时，同步检查 `os/debian/build.sh` 的打包清单、systemd 单元、`os/verify/` 测试和 React API 调用。不要在未更新 CI/打包的情况下批量改文件名。

**English:** This directory owns the Linux guest service stack. It is not a privileged host bridge or a kernel-enforced sandbox. Preserve the exact Agent/Broker/DAG authorization path and the packaging references.
