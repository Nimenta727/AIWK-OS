# Changelog

遵循「工程预览」语义：版本号带 `-preview`，不代表稳定。条目按时间倒序；每次改动的详细记录、验证与下一步见 [docs/routine](docs/routine/README.md)。

## 0.3.1-preview.1 — 2026-11-24

修复版。详细记录见 docs/routine 里 2026-11-23 13:54 与 2026-11-24 的两份日志。

### 修复
- **界面图标全部不显示**：工作台服务的静态资源白名单没有 `.ttf`，图标字体（codicons）一直 404。0.3.0-preview.1 镜像受影响。
- 标签开多后整个窗口被撑宽；AI 文件管理里根目录文件缩进错位；旧页面主按钮对比度 2.5:1；关机按钮图标空白；"新对话"在空对话时点了没反应；中文界面里的英文状态（`DISABLED`、`构建 disabled`、`unavailable`、`Error:` 前缀等）。
- UEFI 启动菜单没有超时（live-build 的 GRUB 模板没有 `set timeout`），会一直等待。
- 发布流程：标签已发布时第一步就停下；有 KVM 时用 KVM；llama.cpp 拉取失败自动重试。

### 变更
- AI 文件管理、持久任务 / 本地模型开关、系统服务与内核三页用统一组件重写；移除 `lucide-react` 依赖和旧样式表 `OsWorkbench.css`。
- 工作台 HTTP 层拆到 `aiws_workbench_http.py`，改成显式路由表；工具平面拆成核心、文件类、系统类三个模块。
- 死代码清理、3 个 SQLite 索引、CSRF 常数时间比较、全部 shell 脚本零 shellcheck 警告。

### CI
- 静态检查加入 ruff 与 shellcheck；新增浏览器巡检作业（`workbench/e2e/ui-audit.cjs`）：对真实服务巡检全部视图、逐个点击按钮、回放镜像内冒烟步骤。

## 0.3.0-preview.1 — 2026-11-23（包含自 0.2.0-preview.1 以来的全部改动）

面向程序员的 AI 原生系统方向：观察台首页 + 本地小模型中转 + 官方 CLI 云端构建 + 开发者工具链。

### 新增
- **本地模型的专用 Agent 接口**（[docs/AIWS_LOCAL_AGENT.md](docs/AIWS_LOCAL_AGENT.md)）：产品模型定为 Qwen3.5-9B（撤出 2B）；OpenAI 兼容客户端（结构化输出按阶梯降级、缓存/用时/令牌只照搬服务端报告）、受约束的 JSON 动作循环（线程/回合/条目，落盘后可逐字节重建请求，工具输出裁剪、确定性压缩、有界并行只读调用）、Agent Skills 格式的技能与 Claude Code 目录约定的插件（只取文字：技能、命令、只会拒绝的守卫；钩子、MCP、脚本一律列出并不运行）、三档路由（local / flash / pro）、`log.digest` / `log.lines` 读日志工具、工作台「本地助手」页（中英双语）。用真实 9B + 真实 `llama-server` 做过端到端验证；没有在真机/显卡上验证。**发布的 ISO 不含模型权重**：客户自行下载，见 [docs/AIWS_MODEL_WEIGHTS.md](docs/AIWS_MODEL_WEIGHTS.md)；QEMU 启动脚本新增 `AIWS_VM_MEM` 与只读的 `AIWS_EXTRA_DISK`。
- **云端模型直接接 DeepSeek API**：自带智能体循环（含受限的编译/测试/运行工具，覆盖 C、C++、Go、Python、Rust、C#、Java、JavaScript）（独立进程，受监督器的预算/隔离/批准约束）、工具由我们执行所以批准是同步的、结构化计划审核、原生子智能体树；密钥只存私有文件、经管道传递。详见 [docs/AIWS_DEEPSEEK.md](docs/AIWS_DEEPSEEK.md)（**未对真实服务验证**）。
- **模型工具箱补齐**：`build_run`（C、C++、Go、Python、Rust、C#、Java、JavaScript、Swift 的固定命令检查/编译/测试/运行）、`deps_install`（经批准的依赖下载）、`git_commit`（仅本地）；项目预览（只读静态服务器）；AIWS Code 作为标签页嵌入工作台。详见 [docs/AIWS_DEV_TOOLS.md](docs/AIWS_DEV_TOOLS.md)。
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
