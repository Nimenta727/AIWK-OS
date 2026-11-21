# Windows workstation & shared React UI

- `AIWorkstation.Desktop/`：Windows WPF/.NET 10 + WebView2 原生宿主。
- `AIWorkstation.Core/`：Windows 本地任务、Agent 编排、计划、Git/证据等核心。
- `AIWorkstation.Core.SmokeTests/`：.NET 核心烟测。
- `AIWorkstation.Frontend/`：共用 React 工作台；`src/os/` 是 Linux 客户机模式页面，不等于 Linux Agent 服务实现。

**不要将 Windows 的用户权限、CLI 执行器或审批记录直接复制为 Linux 可执行能力。** 历史导入遵循 [Windows→Linux 映射规范](../docs/AIWS_WINDOWS_TO_LINUX_AGENT_MAPPING.md)，默认只作审计证据。

Windows 开发入口为根目录 `scripts/Build-NativeDesktop.ps1`；测试/发行参照 [Release checklist](../docs/RELEASE_CHECKLIST.md)。Windows CI 不等于 Hyper-V 实机 GUI/ACL 验收。
