# 2026-11-20 10:38 +08:00 — 原版专业前端一键接入

## 做了什么

- 复核 T3 Code 原版前端、MIT 授权与原生 CLI 的 `serve` 调用方式。
- 将 **启动并连接已安装的 T3 Code** 按钮加入 WPF 原生窗口，用官方 `t3 serve --host 127.0.0.1 --port <port>` 启动服务。
- 连接前先探测已运行的本机服务；已响应时不重复启动服务。
- 保持本机地址校验、WebView2 外部导航拦截、订阅凭据分离和现有的 AIWS 审批/请求链路功能。
- 新增异常端口的回归测试及准确的产品说明，明确「嵌入原版前端」尚不等于「复制了原版源代码」。

## 修改文件

- `desktop/AIWorkstation.Core/T3ServiceLauncher.cs`（新增）
- `desktop/AIWorkstation.Core.SmokeTests/Program.cs`
- `desktop/AIWorkstation.Desktop/ProfessionalShellWindow.xaml`
- `desktop/AIWorkstation.Desktop/ProfessionalShellWindow.xaml.cs`
- `README.md`
- `docs/PROFESSIONAL_FRONTENDS.md`
- 本文件

## 验证

- 静态 XAML XML 解析及 Python 原有回归检查；实际 WPF 编译以 GitHub Actions Windows 任务结果为准。
- 尚需在用户 Hyper-V Windows 虚拟机中核实实际 CLI 版本、端口和官方登录流程。

## 下一步

1. 运行 Windows CI 构建，修复任何 WPF 编译错误。
2. 在 Hyper-V 测试 T3 CLI 已安装/未安装、端口占用、登陆和可视化聊天流程。
3. 在独立分支评估 T3 Code 全栈源码 Fork 和 AIWS 授权适配器，不把未验证的 React 组件直接插进 WPF。
4. 将 AIWS 调度、Token 追踪与成熟前端通过受支持的 API 连接；避免重复存储会话和重复调用模型。


---

## 双语历史摘要 / Historical summary · 2026-11-20

- 中文：本条记录关于 **2026-11-20 10:38 +08:00 — 原版专业前端一键接入**，保留原始日期、修改和验证结论；归档摘要不意味着现版重新验收。
- English: This historical change record covers **professional frontend one click**. Original dates, modifications and verification claims remain intact; no current release acceptance is implied.
- [历史索引 / Timeline](README.md) · [最新 README / Current README](../../README.md)
