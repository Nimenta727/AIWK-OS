# 2026-11-21 · 版权法律处理 + 工具集成进工作台

## 做了什么
**版权法律**
- 新增根 `NOTICE`（Apache-2.0、T3 Code MIT 署名、Code - OSS MIT 与商标声明、Debian 组件说明、第三方产品名归属）。
- 核对历史：全部提交来自仓库所有者账户（含其委托的助手提交），`LICENSE`（Apache-2.0）由所有者本人添加，此前仓库没有 LICENSE 文件 → 没有需要保留的「已按 MIT 发布」授权；相应待办已在 `THIRD_PARTY.md` / `AIWS_OS_BLUEPRINT.md` 更新。
- `package.json` 标 `Apache-2.0`；logo 注释里残留的 "MIT, same as this repository" 已改正；新增 `test_legal.py`（许可一致、NOTICE 内容、MIT 文本保留、不收录 Microsoft 代码/标志）。

**工具集成（工作台为中心）**
- `os/runtime/aiws_apps.py`（已加入 `MODULES`）：内置 / 桌面 / 命令行工具注册表；`launch()` 固定命令、环境白名单、限速、只能按 id。
- 工作台接口：`GET /api/v1/apps`、`POST /api/v1/apps/launch`、`GET /api/v1/workspace/raw`（仅允许图片/PDF/HTML 类型；可执行脚本的类型放入无同源沙箱 + 无网络）、`GET /api/v1/workspace/doc`。页面 CSP 增加 `frame-src 'self'` 与环回地址。
- AI 工具：新增只读 `tools.list`、`doc.text`（pdftotext / pandoc --sandbox，固定 argv，无 shell，输出有界）。
- 本地模型 schema 加入这两个工具后超过网关 20 KB 上限 → 改用 `$defs`，每个工具只描述一次（≈13 KB）。
- 前端：「工具」侧栏；文档阅读器（Markdown 安全解析、CSV 表格、JSON、图片、PDF、DOCX 转文本、沙箱 HTML）；内置预览浏览器（只嵌入本机开发服务与工作区 HTML，外部网站交给 Chromium）。
- 软件包：`poppler-utils`、`pandoc`（对照真实 Debian 索引校验通过）。

## 验证
- Python 404 项、前端 70 项通过；`tsc`、`vite build` 通过。
- 真实 Chromium：Markdown 注入不生效、javascript: 链接惰性；CSV/JSON/图片正常；工作区 HTML 在沙箱里无法访问系统接口；本机开发服务可嵌入；外部网站、javascript:、工作台自身端口均被拒绝；无页面报错。

## 已知问题 / 未验证
- PDF 内嵌渲染和 `pdftotext`/`pandoc` 的真实执行**没有在本环境验证**（测试里用替身验证了参数与错误处理；无头 Chromium 也不一定显示 PDF 查看器）。
- 「AI 自动调用」目前限于只读工具；让 AI 启动桌面程序需要新增一类需审批的写阶段并接入 Broker，**尚未实现**（有意：桌面程序只在你点击时启动）。
- 新的 `$defs` schema 能否被真实 llama-server 的语法转换接受没有验证（失败会回退到普通 JSON 模式）。
- 并非所有「像 Claude/Codex 桌面端那样的大量工具」都已具备：目前是阅读器、预览浏览器、终端/编辑器/文件管理器启动和 17 项注册工具；MCP 外部工具接入、截图/屏幕类工具、网页抓取等没有做。
- pandoc/poppler 为 GPL：随 ISO 分发时须履行源码提供义务（已写入 THIRD_PARTY）。

## 下一步
1. 在真实镜像里验证 pdftotext/pandoc 与 PDF 查看；实际构建 AIWS Code。
2. 设计「AI 启动应用 / 调用外部工具」的审批阶段与 MCP 客户端接入（需要你确认范围）。
3. 其余开源软件候选：图片/音视频播放、SQLite 浏览、Jupyter、Docker 兼容运行时——逐个评估许可与权限模型。
