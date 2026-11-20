# 2026-11-20 23:01 — OS core workbench controller / 系统工作台控制服务

## 变更
- 新增 os/runtime/aiws_workbench.py：跨发行版 Linux 客户机本地 HTTP 服务。连接共享 React 工作台与现有 MCP 代码/文件分析工具。
- 通过单 worker 队列提供状态、结果、错误和任务 ID；只开放明确列入 READ_ONLY 的 API；拒绝远程 Origin、错误 Host、无 CSRF 的写请求、任意 shell、文件写入、浏览器网络操作。
- 新增 os/verify/test_workbench.py：覆盖服务健康、HTML 资源、Host/Origin、CSRF、能力白名单和异步任务返回。
- 改动文件：os/runtime/aiws_workbench.py, os/verify/test_workbench.py, 本记录。

## 验证
- 已新增测试，GitHub CI 结果需在提交后查看。
- 本提交未构建或启动 Linux ISO，也未安装图形会话。

## 已知限制
- 当前 Agent 只是工具任务控制器，并非自主模型推理 Agent。
- 本地 loopback/CSRF 不构成多用户 Linux 隔离；服务器必须以普通用户运行，宿主机保护仍由虚拟机管理程序负责。
- 完整旧 Windows 任务编排尚未迁移。

## 下一步
- 共享 React 前端接入 Linux 模式；将服务打包到 NixOS 和 Debian adapter。
- 添加真实 ISO 构建与 QEMU 启动 smoke workflow，报告实际失败和成功。
- 继续统一任务状态、系统资源/审计、特权 Broker 和隔离验收。
