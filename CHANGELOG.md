# Changelog

遵循「工程预览」语义：版本号带 `-preview`，不代表稳定。条目按时间倒序；每次改动的详细记录、验证与下一步见 [docs/routine](docs/routine/README.md)。

## 0.2.0-preview.1 — 未发布（准备中）

面向程序员的 AI 原生系统方向：观察台首页 + 本地小模型中转 + 官方 CLI 云端构建 + 开发者工具链。

### 新增
- **观察台**（只读首页）：token、模型状态、调用状态、任务、审计结论、待批准；示例数据明确标注为合成回放。
- **VS Code 风格工作台外壳**：活动栏、资源管理器（真实文件树）、标签页、底部面板、状态栏、命令面板、深色/浅色主题、快捷键。
- **本地小模型框架**：懒启动/空闲卸载的模型网关、受约束输出 schema、规则 → 本地模型 → 官方 CLI 的路由；模型只提议，写操作必须审批；完全离线。
- **官方 CLI 构建通道**：一次性授权（目录/预算/工具/时长）、专用低权限用户、nftables 出口限制 + 域名白名单代理、事件库与用量统计（只统计提供方上报数字）。
- **开发者工具链**：额外 53 个 Debian 软件包（Ruby、PHP、Lua、TypeScript、Meson、g++、clangd、valgrind、shellcheck、gh、neovim、tmux 等），包名已对照真实 Debian 索引校验。
- **AIWS Code**：Code - OSS（MIT）重新品牌化构建配方、webview 本地端点补丁、产品配置覆盖与端点/品牌扫描器、启动器、`/api/v1/ide` 接口；保留上游许可与声明。
- **工具集成（以工作台为中心）**：`aiws_apps.py` 统一注册内置 / 桌面 / 命令行工具；`/api/v1/apps`、`/apps/launch`（固定命令、白名单环境、限速、仅按 id）；文档阅读器（Markdown 安全渲染、CSV、JSON、图片、PDF、DOCX 转文本、沙箱 HTML）；内置预览浏览器（只嵌入本机开发服务和工作区 HTML，外部网站交给系统浏览器）；新增 AI 只读工具 `tools.list`、`doc.text`；软件包 poppler-utils、pandoc。
- **工具审批机制**：`app.launch` 写类阶段（需持久化批准 → Broker → Agent → 工作台桌面启动器再验证）；声明式外部只读工具 `ext.rg/jq/gitlog/sqlite`。见 `docs/AIWS_TOOL_APPROVAL.md`。
- **数据集 v3**：v2 逐字保留 + 集成工具样本（`app.launch`、`doc.text`、`tools.list`、`ext.*` 及 3 类新拒绝）；train 882 / dev 122 / held-out 372；模型现在可以**提议**启动程序（仍须审批）。未用 v3 训练真实模型。
- **版权法律**：新增根 `NOTICE`；`package.json` 标明 Apache-2.0；`test_legal.py` 防止文档/许可再次不一致。
- `os/runtime/MODULES`：运行时模块清单，由测试与 `build.sh` 共同使用，取代手写的长 `cp` 列表。
- 文档：重写 README（定位）、`docs/THIRD_PARTY.md`、OS 预览发行说明。

### 移除
- Windows 相关的残留：旧任务历史导入（`aiws_windows_compat.py`、`/api/v1/tasks/import/windows`、界面入口）、跨平台源码模板与 C#/Swift 代码智能（`platform.inspect`、`project.scaffold`、`code.symbols/references/dependencies/platformApis` 共 6 个工具，及 `dotnet/swift` 探测）。操作系统是主线，这些都随旧工作台留在 Git 历史里。模型的工具目录与输出 schema 随之缩小。

### 变更
- 本地模型输出 schema 用 `$defs` 让每个工具只描述一次（13 KB，原约 21 KB，低于网关 20 KB 限制并留有余量）。
- 前端数据获取收敛到共享轮询 hook（页面隐藏时不轮询）；旧样式的硬编码颜色改为主题变量。
- README 与 `os/` 文档中的许可证描述改为与 `LICENSE` 文件一致（Apache-2.0）。

### 已知限制
- AIWS Code 的完整构建、真实客户机里的模型质量、官方 CLI 实跑、完整镜像体积、固件/真机启动均**未验证**。
- Permission Broker 为应用层策略，不是内核强制隔离。
- 发行前仍需 SBOM、模型权重许可确认与根 NOTICE（见 `docs/THIRD_PARTY.md`）。

## 1.9.0-preview.1
Windows 原生工作台预览（WPF/.NET + WebView2）。详见 [docs/history/RELEASE_NOTES_V19.md](docs/history/RELEASE_NOTES_V19.md)（该产品线已移入 Git 历史）。
