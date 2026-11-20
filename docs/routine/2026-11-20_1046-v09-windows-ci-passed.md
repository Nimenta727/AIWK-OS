# 2026-11-20 10:46 +08:00 — V0.9 专业前端 Windows CI 验收

## 做了什么

- 在 Windows CI 中验证新的 T3 Code 原版前端一键启动及 WebView2 桌面宿主编译。
- `Native Windows Desktop EXE` 成功完成 WPF Release build、.NET Core smoke tests 和 `win-x64` self-contained EXE 打包。
- `Python & Windows checks` 成功完成；另在本地运行 Python 回归测试 38/38 通过。
- 核对 GitHub Actions artifact 实际包含 `WindowsAIWorkstation.exe`（65,274,658 字节），以及对应的运行 ZIP。
- Windows EXE SHA-256: `2abe47589f1dee1b245858bfa1e84e9cdba66c89c3f4da9b2f0869b38ef3c19b`。

## 验证来源

- 源代码提交：`995c5638653c941131e69a510caf376eccd136c8`
- Windows CI: https://github.com/Nimenta727/Windows-AI-Workstation/actions/runs/44662724043
- Python & Windows checks: https://github.com/Nimenta727/Windows-AI-Workstation/actions/runs/44662724046

## 与原项目集成的边界

- 使用 Windows WPF EXE 承载正在运行的 T3 Code 原版 UI，而不是不完整的 UI 仿制。
- 原版前端源码尚未直接编译进 AIWS；T3 官方服务及 Claude/Codex 认证仍需用户自行安装和登录。
- 当前 CI 验证了编译与核心行为，不代表用户的 Hyper-V 虚拟机已完成实际 GUI 验收。

## 下一步规划

1. 在用户 Hyper-V Windows 虚拟机内验证 T3 CLI 服务的启动、端口冲突处理和官方认证。
2. 针对 T3 Code 的 MIT 开源全栈构建创建独立实验分支，评估源码级 Fork，避免在主分支直接引入庞大且不兼容的 React 依赖。
3. 利用受支持的接口连接 AIWS 工作流、审批、请求追踪，合并导航体验，避免再次重复生成模型请求。
4. 维持上游许可证声明、固定依赖版本和 Windows CI 自动检查。
