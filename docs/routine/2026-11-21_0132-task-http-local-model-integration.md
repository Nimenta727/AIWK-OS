# 2026-11-21 01:32 — Unified persistent Linux DAG and local model in guest workbench

## 修改
- aiws_workbench.py 的 Controller 接入 aiws_tasks.GuestTaskStore：任务创建、查询、阶段审批、显式阶段调度、任务审计；工具运行同使用 aiws_toolplane.invoke，仅作为单 guest 普通用户。
- HTTP 接口：GET /api/v1/tasks、GET /api/v1/tasks/{id}、GET /api/v1/tasks/{id}/audit；POST /api/v1/tasks、POST /api/v1/tasks/{id}/stages/{key}/approve、POST .../dispatch。所有 POST 共享 Host/Origin/CSRF、JSON payload 上限检查。
- 接入可选本地模型接口 GET /api/v1/model/status、POST /api/v1/model/suggest；默认无模型、不联网/不自动回退云端，模型只产出 read-only 计划，不能执行。
- Debian ISO 打包新增 aiws_tasks.py、aiws_local_model.py；NixOS runtime 已采用 wildcard copy，无需分叉。
- 集成测试增加持久任务 API / DAG 执行 / 审计 / 禁用离线模型结果，关闭时清理 SQLite。
- 文件：os/runtime/aiws_workbench.py、os/debian/build.sh、os/verify/test_workbench.py、本 routine。

## 限制与验收
该统一任务内核是 Linux 端的可持久化基础，尚未涵盖 Windows 原有 DAG 的所有特殊状态/调度协议。未提供自动长期运行、任何宿主 API、任意 shell 或特权代理。UI 仍需增补同一任务视图以及真实图形交互测试。实际 CI 验证以后结论为准，不能凭提交说已成功 boot。

## 下一步
工作台任务/DAG/审批界面，独立小模型建议面板；Qwen3.5-2B opt-in llama-server guest service 配方、评测集；真实 GUI 点击/固定内核配置；NixOS boot。
