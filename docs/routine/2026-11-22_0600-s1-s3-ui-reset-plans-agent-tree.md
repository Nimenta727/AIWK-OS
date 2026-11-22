# 2026-11-22 06:00 — S1–S3：前端重置、计划审核区、云端子智能体树

## 改动
- **前端重置**：新增 `workbench/src/ui/`（令牌、基础样式、组件库、布局）和 `workbench/src/app/`（外壳与页面），入口改为新 `App`；旧的 `OsWorkbench/Shell/Observatory/SystemControls/ChangesView` 和 `shell.css` 已删除。图标改用 Codicons（固定版本），光标、焦点、分隔条拖动与键盘操作见 `docs/AIWS_UI_DESIGN_SYSTEM.md`。
- **计划审核区**：后端 `aiws_plans.py`（风险由平台按工具类别计算，不信任模型自报；文字计划按列表格式拆步骤并标注“解析自文字”，只给关键词提示，不下结论；TodoWrite 结构化读取）、`GET /api/v1/plans`、适配器与监督器把 `TodoWrite/ExitPlanMode` 送入计划库（正文不进事件库）。前端 `Plans.tsx`：逐步表格、风险徽标、依赖、状态、单步批准，高风险需二次确认，“批准全部低风险”。
- **云端子智能体树**：事件模式新增 `node/parent/model/label/ctx/prog`；Claude 适配器识别 `parent_tool_use_id`、Task/Agent 派出、`task_started/task_notification`；`aiws_agent_tree.py` 重建树（模型继承会标注，未报告就是未报告，环/自指/节点数有界）；`GET /api/v1/observatory/tree`；前端 `AgentTree.tsx`：树 + 详情（状态、模型、进展、token、上下文链接，文件可点击打开）。
- 测试中发现并修复：我最初把子智能体的“类型”（如 reviewer）当成了模型，已改为只认显式 model，类型放进标签。
- 合规更正：Codicons 的图标是 **CC-BY-4.0**（不是 MIT），已在 `NOTICE`、`docs/THIRD_PARTY.md` 署名。

## 验证
- Python 493 项通过（新增 tree 11、plans 13、ui_api 3）；前端 `tsc`、`npm test` 40 项、`vite build` 通过。
- 真实 Chromium（API 用夹具模拟，服务本身未启动）：深/浅主题总览、计划、智能体树、变更、系统页截图人工查看，无控制台错误。发现并修复：侧栏内容没撑满、状态圆点不带颜色；浅色主题按钮截图“发黑”经等待确认为过渡中截图，非缺陷。
- **未验证**：Claude Code 真实 stream-json 的字段名（`parent_tool_use_id`、`task_*` 事件）——按公开资料和社区实现编写，样本是合成的；真实服务 + 真实数据下的页面；窄屏；键盘走查。

## 已知问题
- 4 个旧页面（AI 文件管理、持久任务与 DAG、本地 AI 助手、系统服务与内核）还是旧组件，仅映射了颜色变量，未按新规范重写。
- 云端计划无法逐步拦截（CLI 自己决定步骤），界面已如实说明，约束来自授权范围。
- 子智能体“上下文链接”目前只有该节点读过/用过的文件、搜索、命令、提示长度，不含它收到的完整提示正文（事件库不存正文）。

## 下一步
S4 本地模型常驻与推理框架；S5 双盘/三用户系统文件；之后重写 4 个旧页面，并用真实 CLI 录制校对事件字段（O6）。
