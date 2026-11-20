# 2026-11-20 10:32 +08:00 — 上游原版前端容器 Windows CI 验收

## 已验证改动

- 已将原版 T3 Code / OpenClaw 前端本地嵌入容器作为 Windows AI Workstation V0.8 的默认启动窗口。
- GitHub Actions **Native Windows Desktop EXE** run [44660930497](https://github.com/Nimenta727/Windows-AI-Workstation/actions/runs/44660930497) 完成，结果 **success**，覆盖 .NET 10 WPF 编译、核心 smoke tests、Windows x64 自包含单文件 EXE 和 artifact 上传。
- Python & Windows checks run [44660930448](https://github.com/Nimenta727/Windows-AI-Workstation/actions/runs/44660930448) 完成，结果 **success**。
- 构建包经 ZIP 检查确实包含 `WindowsAIWorkstation.exe`，约 65MB。
- 更新 README 中已过时的“待 CI”字样，说明 Hyper-V 来宾系统 GUI、WebView2 与官方本地服务连通性仍未实测。

## 涉及文件

- `README.md`：注明 Windows CI 已通过及尚需的运行时验证
- `docs/routine/2026-11-20_1032-upstream-ui-windows-ci-verified.md`：本次记录

## 尚未完成

- 没有复制 T3 Code / OpenClaw 的完整 React 前端源码；当前是上游**原版界面运行时嵌入**，非完整源代码移植。
- 未自动安装或启动上游平台，也未合并各项目会话和任务数据库。
- 尚未在用户的 Hyper-V Windows 虚拟机上实测真实 GUI 与登录。

## 下一步规划

1. Windows 虚拟机安装运行包、确认 WebView2 Runtime、启动 T3 本地 Web 服务和 OpenClaw Gateway，验证导航与权限。
2. 评估将 MIT 许可的 T3 Code 前端以固定版本 fork 的方式真正迁移到仓库，保留其原始依赖与许可声明。
3. 为 AIWS 原生流程和上游界面建设有文档支持的适配接口，并合并任务导航；不得复用未经授权的订阅 Token。
4. 添加 Hyper-V 图形界面端到端测试，确保主题、缩放、登录和掉线处理可靠。
