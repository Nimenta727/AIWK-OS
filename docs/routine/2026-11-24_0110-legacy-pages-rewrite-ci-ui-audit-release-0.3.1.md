# 2026-11-24 01:10 — 三个旧页面重写、浏览器巡检进 CI、发布 0.3.1-preview.1

## 背景
上一轮前端审计留下三件事，用户回复"都做了"：
1. 发布修复版 0.3.1-preview.1（让用户拿到有图标的镜像）。
2. 把三个旧页面改写成新组件库、去掉 lucide。
3. 把审计脚本放进仓库，作为 CI 的浏览器检查。

## 1. 三个旧页面重写
- `workbench/src/os/GuestFiles.tsx`（AI 文件管理）、`GuestTaskStudio.tsx`（持久任务 / 本地模型开关）、`GuestSystemConsole.tsx`（系统服务与内核）全部改用 `Section / Row / Button / IconButton / Input / Select / Badge / Notice / Empty`，图标只用 codicons。
- 行为不变：每个改动仍然先生成审批卡片或 DAG 任务；请求都走共用的 `api()`。
- **顺带修掉的问题**：
  - 服务与内核页原来三项数据（服务、内核、审计）任一读取失败，另外两项也一起显示为空 → 改为各自加载（`Promise.allSettled`）。
  - "运行客户机阶段"在依赖阶段还没完成时也能点 → 现在禁用并说明原因。
  - 模型名放在小节标题里会被 CSS 转成大写（"QWEN3.5-9B"）→ 改为单独一行显示。
- 阶段状态显示为中文徽章（待执行 / 执行中 / 已完成…），机器可读的状态放在 `data-state` 属性里。
- 移除 `lucide-react` 依赖（`BrowserView` 也改用 kit）和旧样式表 `OsWorkbench.css`（182 行）；新样式是 `app.css` 里约 20 行 `.gp-*`。
- 打包后 JS 从 389.7 kB 降到 378 kB。
- **镜像内冒烟测试同步更新**（`aiws_gui_smoke.py`）：文件树行现在是 `role=treeitem`；阶段完成读 `data-state="completed"`。其余钩子（`.aiws-os-file-list`、`.aiws-os-file-detail pre`、`.aiws-os-studio`、`.aiws-os-stage-status`、`.aiws-os-system-console`）和按钮文字保持不变。

## 2. 浏览器巡检进仓库和 CI
- `os/verify/fixtures/serve_workbench.py`：在临时演示工作区上运行**真实**工作台服务（含冒烟用的示例文件；有 git 时初始化仓库，让"变更审查"有内容可看），SIGTERM 时清理临时目录。
- `workbench/e2e/ui-audit.cjs`，三部分：
  - **巡检**：深色 1440、浅色 1440、深色 1024 三种设置下的 13 个视图。不通过的情况：
    - 页面异常、整页横向滚动、文字截断或溢出编辑区；
    - 没有处理函数的控件、无名按钮、空白图标、**图标字体没有加载**；
    - 对比度不达标、中文界面里的整句英文；
    - 界面文件（字体、脚本、样式、图片）加载出错。
  - **点击**：每个可用按钮点一遍，没有效果即失败；关机接口在网络层被拦截。
  - **回放**：镜像内冒烟的 4 个步骤。
  - API 的 HTTP 错误只报告不判失败（环境决定，例如非 root、没有 Agent 服务）。
- **变异检验**：去掉 `.ttf` 后，第一版脚本**没有发现**问题（CSS 里的图标字符照样存在，只是字体没到）→ 加了"codicon 字体必须已加载"和"界面文件不能出错"两条。之后再去掉 `.ttf` → 每个视图都失败，并列出 404 的字体文件。
- `.github/workflows/aiws-os-static.yml` 新增 `ui-audit` 作业：构建 → 安装固定版本 `playwright@1.63.0`（`--no-save`，不进产品依赖）和 Chromium → 巡检 → 上传截图和 report.json（保留 14 天）。

## 3. 发布 0.3.1-preview.1
- `release/PREVIEW.env`：标签 `v0.3.1-preview.1`，`full` 阶段。只有构建、内容检查、QEMU 启动和镜像内冒烟全部通过才会发布。
- 发布说明（工作流内）新增"本版修复"一节。其中 UEFI 菜单超时写明**尚未在真实 UEFI 启动里验证**：这个流程的启动测试直接引导内核，不经过菜单。
- `CHANGELOG.md` 新增 0.3.1 与 0.3.0 两节（原标题"0.2.0 未发布"已过时）；`docs/RELEASE_NOTES_OS_PREVIEW.md` 与 `workbench/package.json` 版本同步。

## 验证
- Python 全量 **926 通过，2 跳过**；前端严格 `tsc`、`vite build`、**46 项**单元测试通过；ruff 通过。
- 本地 UI 巡检：39 个视图组合全部通过，31 个按钮全部有效，冒烟回放 4/4。
- 推送前先等 CI 的静态检查和新浏览器作业变绿，再改 `PREVIEW.env` 触发发布。结果见文末。

## 已知问题
- 巡检的数据仍然稀少（计划、云端运行、会话为空），满数据时的布局没有覆盖。
- 本地模型开关页里仍然带着"创建持久化任务"表单（以前就是这样），信息偏多。
- UEFI 菜单超时只用单元测试证明了配置文本，镜像级的固件启动验收仍只在 main 上运行。

## 下一步
1. 给巡检加一份"满数据"的演示状态（几个计划、一次云端运行的事件流）。
2. 让固件启动验收（`aiws-os-image-boot.yml`）也能在分支上手动触发，用来验证 UEFI 菜单。
3. 拆开模型开关页和任务表单。

## 结果
（发布运行结束后补记）
