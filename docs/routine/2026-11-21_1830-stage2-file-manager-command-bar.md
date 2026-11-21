# 2026-11-21 18:30 — 阶段 2：文件管理器、指令栏、批准卡片、撤销

## 改动
- 后端：`workspace.tree` 返回 `dirs`；新增只读工具 `file.trashList`（已登记 Broker 直读/Agent 直读/Workbench 只读/任务 TOOLS）；新增 `GET /api/v1/workspace/stat`、`GET /api/v1/workspace/trash`。
- 前端：`os/GuestFiles.tsx` 重写（目录树、新建/移动/复制/移到回收站、回收站面板、批准卡片、撤销）；`os/OsWorkbench.tsx` 顶部加入指令栏；`model/fileOps.mjs` 纯逻辑；样式见 `OsWorkbench.css`。
- 测试：`test_fileops.py` +2、`test_workbench.py` +2（HTTP 全流程：mkdir→move→trash→restore，批准前不生效）；`tests/fileOps.test.mjs` 5 项。
- 文档：`AIWS_NATIVE_AI_PLAN.md` 更新状态与阶段 2 说明。

## 验证
- Python：`unittest discover -s os/verify`：125 项通过。
- 前端：`tsc --noEmit` 通过；`npm test` 45 项通过；`vite build` 成功。
- 真实浏览器（Chromium/Playwright，对真实工作台服务）：批准前磁盘无变化；批准后新建/移动/删除到回收站生效；“撤销”恢复成功；未识别指令与 `../` 越权路径被拒；无页面错误。
- **未验证**：QEMU 客户机内 GUI、经 Agent/Broker IPC 的 singleton 生产路径（本次测试走进程内路径，与既有 file.replace 测试相同）。

## 已知限制
- “放弃”只关闭界面卡片，任务阶段保持 pending；无审计级“拒绝”状态。
- 目录复制、永久清空回收站暂不支持。

## 下一步
1. 阶段 3：模型工具分级与多步计划（自然语言 → 批准卡片）；系统/网络只读工具；下载策略与下载管理（模型自主执行，策略内免逐次审批）。
2. 阶段 4：模型路由（官方 CLI，用户确认后升级）。
3. 在 CI 的 QEMU GUI 测试里加入文件管理器流程。
