# 2026-11-21 01:04 — Guest file composition UI in the shared AIWS workbench

## 改动
- 新增 Linux OS 工作台 AI 文件管理页面，React 直接使用 guest-only API 读取文件组成、文件内容、SHA-256；无需传统 Linux 文件管理器。
- 可选手动文本编辑向已提交的 guest file.replace 任务队列发送带旧 SHA-256 的请求；不能直接修改主机文件，UI 不能假定提交等于成功。
- 保留 Linux 模式与 Windows WebView2 共用的 React 入口，不更改 Windows/WPF 通信协议。
- 受影响：desktop/AIWorkstation.Frontend/src/os/GuestFiles.tsx, OsWorkbench.tsx, OsWorkbench.css, 本 routine。

## 测试和限制
需 GitHub native-desktop 工作流 TypeScript/Vite 编译与浏览器检查；尚未在真实 Linux VM 中点击验证。文件浏览 UI 并非自主小模型，跨文件重构/文件组织自动化仍须在后续 Agent 计划和权限链路中实现。

## 下步
沿 docs/AIWS_OS_PRIORITY_GATES.md 强制顺序推进：工作台实际 GUI 显示与交互、迁移 Windows 持久任务/DAG、真实 NixOS boot、guest-only broker/资源与恢复。离线 1–3B 模型只作为可选计划器，不引入宿主操作权限。
