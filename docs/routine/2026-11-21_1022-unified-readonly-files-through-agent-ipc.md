# 2026-11-21 10:22 — Make deterministic file reads and directory listing use the same guest Agent

## 实际代码
- 独立 aiws-agent.service 的私有 Unix IPC 新增 tool.read，仅允许 workspace.tree/file.read/代码索引等固定只读工具，严格验证参数表，拒绝 file.replace、runtime.test、host 命令、系统服务 mutation。系统文件读取仍使用 guest toolplane 工作区路径/挂载拒绝逻辑。
- aiws_workbench.py 在生产 singleton 模式的目录和文件 GET API 改为转发给 Agent IPC，避免工作台自行执行文件操作。离线 embedded 测试模式保留原实现，并在所有路径中执行相同工具校验。
- aiws_agent_client.py 新增 ReadOnlyToolProxy；test_agent_service.py 新增跨 socket 正常文件读取、拒绝直接写入、拒绝 runtime.test 测试。
- UI 的文件写仍必须先创建持久 DAG、经批准后执行；文件读取不需要模型 Token。
## 文件
aiws_agent_service.py、aiws_agent_client.py、aiws_workbench.py、test_agent_service.py、本 routine。
## 后续
CI 静态/Windows + 实际 QEMU/系统服务验证及内核 B→A、真实本地模型性能基线；目标是完整消除执行器双轨，仍需长期稳定性回归。
