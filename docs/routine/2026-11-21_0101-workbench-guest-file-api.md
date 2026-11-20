# 2026-11-21 01:01 — Guest-only file access unified under workbench API

## 变更
- Linux 客户机工作台新增 workspace/tree 和 workspace/file HTTP API，后端仅代理已有 MCP workspace.tree 和 file.read，所有访问仍经过 guest workspace、共享挂载拒绝、符号链接、大小和受保护元数据的检查。
- 将 **客体内** file.replace 纳入 Agent 可调用工具目录；修改必须附带旧 SHA-256，工具原子写入文件并记录审计，冲突拒绝。仍不允许 runtime.test、任意 shell、用户主机、项目 scaffold 或外网 browser。
- 新增 HTTP 集成测试：文件树、内容/哈希、拒绝读取 /etc/passwd、合法客户机文件编辑、旧 SHA 冲突拒绝。
- 文件：os/runtime/aiws_workbench.py, os/verify/test_workbench.py, 本 routine。

## 验证
需通过本次 AIWS OS static GitHub Actions；此步骤是后端文件管理 API，GUI 点击与传统文件系统管理器替代尚未验收。

## 风险和限制
仅允许独立虚拟机内工作区。HTTP 单用户环境与 VM 检测不是强安全沙箱；宿主 VM 管理器必须禁用 host shared mounts、host bridges、设备直通与 hypervisor control。未经 Git 审查的模型自主改写和内核热修改不在此次范围。

## 后续
工作台新增客体文件结构可视化/可选手动编辑；持久化统一任务计划/DAG；NixOS ISO/GUI；受控 guest-only kernel image 管线与回滚。
