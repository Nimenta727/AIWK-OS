# 2026-11-21 12:09 — Windows WorkTask/DAG 历史安全导入同一 Linux Agent

## 本次改动
- 新增 `os/runtime/aiws_windows_compat.py`，解析现有 Windows `WorkTask`、`WorkflowStep`、`UnifiedTaskState` 字段。保留原始 32 位任务 ID、阶段 ID 与 DAG 依赖；非 GraphMode 的旧线性任务按 Windows Sequential Ready 语义重建依赖顺序。
- 保留原阶段状态、Agent 类型、Windows 审批声明、计划修订的 SHA256、工件 SHA256、运行记录元数据，**不导入原 Windows 提示词、指令正文、结果正文、原审计 metadata 文本或令牌记录**；仅保存 Hash、计数和受界元数据。
- `GuestTaskStore` 增加 `windows_imports` 表和 `import_windows`，原任务导入同一个 SQLite / 独立 systemd Agent。阶段进入 `unmapped` 状态、`windows.unmapped` 工具占位、`approval=0`，绝不自动执行，也不允许直接 dispatch/approve。
- 独立 Agent IPC 新增 `task.import_windows`，工作台增加带 Host/Origin/CSRF、16KiB 限额的 `POST /api/v1/tasks/import/windows`；对只携带 task JSON 的导入请求强制验证。
- Debian 13 ISO 打包导入模块。添加纯转换/重启/拒绝执行回归及 HTTP CSRF/导入回归测试。
- 修改文件：adapter, tasks, Agent Service, Client, workbench, Debian build, 两份 tests, 本日志和 routine 索引。

## 安全和语义界限
- **这是历史状态导入，不是 Windows 命令或 Claude/Codex 执行适配。** Win Agent 的 Completed 等历史状态只作为原始记录，Linux 工作流状态永远是 unmapped，不能绕过客体审批去执行。
- 仅允许接收客户端主动提交的 JSON 对象；绝不支持读取宿主 C:/ 路径、Host 挂载、VM bridge、root/shell 或 Docker daemon。
- 目前可导入单个不超过 16KiB 的 Windows WorkTask，最多 32 stages；超限要后续设计数据迁移流，不应放松请求安全边界。Windows 完整历史执行日志、200-step DAG、所有适配器/版本修订的 1:1 迁移尚未实现。
- 提交后实际 CI 结果为准，不把协议测试等同 QEMU 生命周期完成。

## 下一步
1. AIWS Shell 增加 Windows 导出文件选择和安全迁移预览，对 unbound stage 提供清晰只读标记。
2. 设计用户确认后的受限 Tool Mapping/审批与计划修订；保留原始阶段 ID、artifact provenance。
3. 建立跨 C# Windows 真实 JSON fixtures 与 Python 兼容验证；持续检查本地 2B 模型实际 CPU 和 QEMU 推理。
