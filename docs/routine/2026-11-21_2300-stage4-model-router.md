# 2026-11-21 23:00 — 阶段 4：模型路由

## 改动
- 新增 `os/runtime/aiws_model_router.py`（规则路由、`after_local` 升级限制、交接文件、严格配置）；已加入 `os/debian/build.sh` 打包清单（并有回归测试防止漏打包）。
- `aiws_workbench.py`：`model_plan` 先路由；新增 `/route`、`/route/handoff`、`/route/config`；本地失败返回 `followUp`；拒绝返回最终 `followUp`。
- `aiws_tasks.py`：`record_route`（仅哈希）；Agent IPC `task.route`；`TaskProxy.route`。
- 前端 `GuestTaskStudio.tsx`：路由卡片、交接按钮、拒绝为最终结论的提示、外部开关状态说明。
- 测试 `test_router.py` 26 项；文档 `AIWS_MODEL_ROUTER.md`，更新 `AIWS_NATIVE_AI_PLAN.md`、runtime README。

## 评测记录（如实）
锁定集 v2 一次性结果：135/142 本地、96/100 不可外发；据此修复两个通用缺陷后该集对路由器已“污染”，仅作回归。

## 验证
- Python 全量单元测试通过；前端 `tsc`/`vite build` 通过。
- 真实浏览器（回环 mock 模型）：外部默认关闭→“手动”卡片无任务；下载请求→模型拒绝→最终、无交接按钮；启用后→交接按钮→批准前磁盘无变化→批准后 `handoff/*.md` 含指令和文件名、**不含文件内容**；受限请求即使启用也无交接按钮；无页面错误。
- **未验证**：真实 CLI（本系统从不启动它们）；真实 2B 模型；QEMU 内 GUI。

## 下一步
真实客体上跑 v1/v2 取基线；路由规则用独立作者的措辞再评测；审计级“拒绝/放弃”状态；QEMU GUI 流程测试；配置的安全编辑方式。
