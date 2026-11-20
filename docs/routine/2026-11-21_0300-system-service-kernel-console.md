# 2026-11-21 03:00 — Native AIWS system service and kernel candidate console

## 本次改动
- 新增 desktop/AIWorkstation.Frontend/src/os/GuestSystemConsole.tsx 作为 AIWS 系统与安全主页面，真实读取客户机用户级 aiws-workbench/aiws-local-model 服务状态、运行内核版本及 SQLite 审计哈希链健康状况。
- 系统管理只能创建持久 DAG 审批任务：服务重启仅允许 aiws-local-model.service；kernel.stage 先从 guest workspace 获取配置文件及 SHA-256，再提交需明确审批的任务；kernel.verify/recovery_plan 和 abandon 均使用同一任务接口，其中 abandon 必须审批。
- 页面明确区分可验证的候选暂存和**尚未实现的真实 A/B bootloader 回滚**，不会误标记内核修改成功。UI 不提供系统 root、任意 shell、VM 管理或宿主机文件调用。
- OsWorkbench.tsx 将旧静态系统状态页替换为客户机管理主控页面；OsWorkbench.css 添加服务/候选状态样式，导航与 Windows 桌面入口保持原状。

## 修改路径
desktop/AIWorkstation.Frontend/src/os/GuestSystemConsole.tsx、OsWorkbench.tsx、OsWorkbench.css、本 routine。

## 验证/下一步
需 Native Windows Vite/TypeScript 与 Debian ISO/QEMU 编译/启动/GUI 自动化。当前 Python 合同测试已对系统接口做只读/host-deny 测试，仍需补 UI 系统页交互自动化、完整内核构建与可靠 A/B boot 恢复以及本地 Qwen 2B 真正推理。
