# 2026-11-21 · VS Code 风格前端外壳 + AIWS Code 启动接口

## 做了什么
- **前端外壳**：工作台改为 VS Code 布局：活动栏（观察台 / 资源管理器 / 任务 / AI / 系统）、侧边栏（真实的工作区文件树）、标签页编辑区、底部面板（任务 / 最近事件）、状态栏（服务、本地模型、构建、待审批、token、审计结论）、命令面板（Ctrl+Shift+P / F1）。
- **主题**：深色（默认）/ 浅色，全部通过 `--c-*` 变量；旧样式里写死的浅色用 `scripts/tokenize_colors.py` 一次性转成变量。偏好（主题、侧栏、面板、当前活动）存 localStorage，读写均有异常保护。
- **只读文件查看器**：点击文件树在标签页中查看（走已有的受限 `file.read`，拒绝二进制/软链接/超大文件）。
- **后端**：`GET /api/v1/ide`（是否安装、是否运行、版本、端口）与 `POST /api/v1/ide/open`（CSRF、空载荷、固定命令、白名单环境、5 秒限速）。
- **收敛**：观察台数据改为一个共享轮询 hook（页面隐藏时不轮询），`Observatory` 只负责展示。

## 改动文件
- 前端：`src/os/{OsWorkbench.tsx,Shell.tsx,FileViewer.tsx,shell.css,api.ts,observatoryTypes.ts,useObservatoryData.ts,Observatory.tsx,OsWorkbench.css}`、`src/model/shell.mjs`、`tests/shell.test.mjs`、`scripts/tokenize_colors.py`
- 后端：`os/runtime/aiws_workbench.py`、`os/verify/test_ide_api.py`

## 验证
- `tsc --noEmit` 通过；`npm test` 61 项通过；`vite build` 成功。
- Python 全量 380 项：开始时 1 项失败（`test_ide_api` 读文件的竞态，已修：等待脚本最后一行再断言），单独连跑 3 次稳定通过。
- 真实浏览器（Chromium + 演示数据）：深色/浅色截图、打开文件标签、命令面板过滤并执行、Ctrl+J 面板、切回观察台，无页面报错。

## 已知问题 / 未验证
- 旧的"高级工具"页面内部仍沿用原有卡片样式，只是换了配色变量；个别细节在深色下可能不够精致。
- 观察台侧栏里的"结论"目前直接显示等级英文词（如 yellow）。
- AIWS Code 本体（VS Code 源码构建）仍未在本环境构建；"打开 AIWS Code" 只验证了接口与启动器，没有真实启动编辑器。
- 窄屏（<820px）侧栏为浮层，未做真机/手机验证。

## 下一步
1. 整理代码结构（`build.sh` 运行时模块清单化、对齐 `os/model/aiws-local-model.sh` 与安装版、更新 `docs/CODEBASE_MAP.md`）。
2. 重写 README，突出系统定位（面向程序员的 AI 原生操作系统、自然语言驱动、观察台为首页）。
3. 发行准备：VERSION、CHANGELOG、第三方许可清单、发布检查表（标注 preview）。**打 tag / 发布前先征求你的确认。**
