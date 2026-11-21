# 2026-11-21 · 移除残留的 Windows 相关代码；修复启动冒烟的界面选择器

## 做了什么
- **删除**：`aiws_windows_compat.py`、`aiws_crossplatform.py`、`aiws_codeintel.py` 及对应测试；任务库里的 Windows 导入表/方法、Agent/Workbench 的导入接口、前端的“导入 Windows 工作流历史”卡片与“代码智能”页；工具目录里的 6 个 Windows/macOS/C#/Swift 工具与 `dotnet/swift` 探测。文档：3 份移入 `docs/history/`，其余文档中的 Windows 说法逐处改写。
- **v1 数据**：删掉引用已删工具的 3 行训练样本和 4 行留出样本（v2/v3 不受影响），测试期望值同步。
- **发现并修复一个会让发行失败的潜伏问题**：镜像里的启动冒烟（`aiws-boot-smoke`）①用 `code.symbols` 当“MCP 可用”的探针；②调用的 GUI 冒烟脚本仍使用旧界面（`<nav>` 菜单）的选择器——VS Code 风格改版后它必然失败，而发行工作流要求启动冒烟通过才发布。已改为探测 `workspace.tree`，GUI 冒烟改用命令面板导航并去掉 Windows 导入步骤；用 Playwright 在真实新界面上逐步复现（文件列表点击读取、DAG 保存并运行到 COMPLETED、本地模型页显示 DISABLED、系统控制台渲染）全部通过。
- 前端：删除未用导入，`tsc --noUnusedLocals` 通过；`index.html` 标题改为 AIWK-OS。

## 验证
- Python 全量与前端测试通过（见下方提交说明）。**本地 live-build 完整配置（`AIWS_OS_PROFILE=full`）成功构建出 ISO**（2.09 GB，未含模型权重与 AIWS Code）——软件包清单、钩子与配置在真实 Debian 13 环境里可构建。
- 没有在本环境里真正启动该 ISO（无 KVM/QEMU 验证）；启动冒烟与真实 Selenium 版 GUI 冒烟需要在 Actions 的 QEMU 中验证。

## 已知问题
- 真实 Selenium 版 GUI 冒烟的最后一段（内核候选的批准/暂存）沿用旧选择器，但那些是 `GuestTaskStudio`/`GuestSystemConsole` 里未改动的组件；仍需在真实启动中确认。

## 下一步
- 等 Actions 的 AIWS Code 构建结果；然后 `iso-dry`（构建+启动）→ `full`（发布）。
