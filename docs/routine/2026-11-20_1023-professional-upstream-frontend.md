# 2026-11-20 10:23 +08:00 — 专业平台原版前端集成

## 本次改动

- 新增 Windows 原生 `ProfessionalShellWindow`，启动即进入成熟平台前端容器，原 WPF 窗口从默认首页移为「AIWS 任务与流程」。
- 使用微软 WebView2 原样显示用户本机运行的 T3 Code 或 OpenClaw 前端，**不是**手绘仿制品。新增两平台切换、本机服务地址栏、服务探测及连接状态。
- 默认只允许回环地址，禁止嵌入外部网页与任意 WebView2 消息通道。设置仅保留不含 Token 的本机地址。
- 增加 `LocalFrontendEndpoint` 的白名单及来源校验与核心 smoke tests。
- 引入官方 `Microsoft.Web.WebView2` NuGet 依赖，保留现有 .NET Core 执行基座。
- `README.md` 与 `docs/PROFESSIONAL_FRONTENDS.md` 精确说明源码迁移边界和真实集成状态。

## 修改/新增文件

- `desktop/AIWorkstation.Core/LocalFrontendEndpoint.cs`
- `desktop/AIWorkstation.Core.SmokeTests/Program.cs`
- `desktop/AIWorkstation.Desktop/ProfessionalShellWindow.xaml`
- `desktop/AIWorkstation.Desktop/ProfessionalShellWindow.xaml.cs`
- `desktop/AIWorkstation.Desktop/App.xaml.cs`
- `desktop/AIWorkstation.Desktop/AIWorkstation.Desktop.csproj`
- `README.md`
- `docs/PROFESSIONAL_FRONTENDS.md`
- `docs/routine/2026-11-20_1023-professional-upstream-frontend.md`

## 验收状态

- 本地静态检查可运行。当前开发容器未安装 .NET SDK，故 WPF 构建以 GitHub Windows CI 为准。
- 尚未连接用户 Hyper-V 虚拟机；上游软件须先由用户启动相应官方服务。
- V0.8 是原版前端**运行时嵌入**，还不是将上游 React 源代码复制入仓库。不会宣传为源代码完整迁移。

## 下一步规划

1. 通过 Windows CI 编译和 smoke tests，解决任何阻断问题。
2. 在 Hyper-V Windows 来宾验证 WebView2、T3 Code、OpenClaw 服务、CLI 登录及窗口行为。
3. 以单独许可保留与版本锁定的方式评估完整 T3 Code 前端 fork，建立 AIWS workflow adapter。
4. 合并工作台导航和审批 UX，持续减少两个平台之间切换造成的无效请求。


---

## 双语历史摘要 / Historical summary · 2026-11-20

- 中文：本条记录关于 **2026-11-20 10:23 +08:00 — 专业平台原版前端集成**，保留原始日期、修改和验证结论；归档摘要不意味着现版重新验收。
- English: This historical change record covers **professional upstream frontend**. Original dates, modifications and verification claims remain intact; no current release acceptance is implied.
- [历史索引 / Timeline](README.md) · [最新 README / Current README](../../README.md)
