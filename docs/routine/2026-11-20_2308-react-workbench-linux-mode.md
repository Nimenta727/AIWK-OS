# 2026-11-20 23:08 — Shared React workbench supports Linux guest mode

## 中文
**变更：** 复用 Windows 工作台的 React/Vite 工程，不克隆第二套界面。main.tsx 仅在客户机本地服务注入 os-bridge.js 时启用 Linux 工作台，Windows WebView2 路径继续保留。新增系统概览、代码智能工具、Agent 任务队列、系统/隔离诊断，前端请求现有 loopback API 并显示真实响应，不伪造自主推理或 OS 管理能力。
**文件：** desktop/AIWorkstation.Frontend/src/main.tsx; desktop/AIWorkstation.Frontend/src/os/OsWorkbench.tsx; desktop/AIWorkstation.Frontend/src/os/OsWorkbench.css; 本记录。
**验证：** 等待 native Windows workflow 完整 TypeScript/Vite 编译和 UI 测试；当前未在 Linux VM 中运行或启动图形会话。
**限制：** Linux 工作台只包含 OS MVP 页签，尚未移植 Windows 核心任务数据库和完整 Agent 调度协议，也不含自主模型执行。界面 CSP 和 HTTP 不提供跨本地用户隔离。
**下一步：** 检查 CI 编译错误并修复；将共享 UI 构建结果装入 NixOS / Debian 镜像；联调开机服务、图形会话及 Agent 任务。
## English
Share a single React source tree between the Windows WPF host and Linux guest mode. The guest-only entry adds real system health, local task queue and code tools, with no fabricated execution telemetry. Validate in Windows frontend CI before guest boot testing.
