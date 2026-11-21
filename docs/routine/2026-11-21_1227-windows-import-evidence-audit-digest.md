# 2026-11-21 12:27 — Windows 迁移历史元数据与统一审计链哈希绑定

## 修改
- Windows WorkTask 历史导入时，在 `windows.history_imported` 审计事件中记录完整**受界元数据**的 SHA-256，不记录 Windows 原始提示词、工具日志和输出文本。
- 每次 `GuestTaskStore.get()` 读取被导入的旧任务时，将 windows_imports 元数据再次计算哈希，与同一任务的原始审计回执比对；不一致时明确失败，不把已篡改历史静默显示成可信。
- `test_windows_compat.py` 增加故意修改 SQLite windows_imports 元数据行的回归，确认读取拒绝且恢复数据后审计仍可验证。
- 修改：`os/runtime/aiws_tasks.py`、`os/verify/test_windows_compat.py`、本 routine 及目录索引。

## 验证与限制
- 需要本次 OS 静态和 Python CI 实际通过。此哈希绑定只针对普通 SQLite 数据完整性；可控制 guest root 或完整数据库与审计链的攻击者仍可能伪造，不能宣称硬件可信证明。
- Windows 导入阶段仍全部为 `unmapped`/不可执行。任何后续映射均需要用户审批；不读取宿主机文件。
- 独立模型推理 CI 与本变更无关，仍在按固定 llama.cpp 二进制实际运行。

## 后续
1. 真实 QEMU GUI 选择 Windows JSON、显示 UNMAPPED 阶段、跨 Agent 服务重启不丢失回执。
2. Windows UnifiedTaskCore 的计划版本、工作项以及人工审查后 Tool Mapping 的受控迁移。
3. 继续验证本地 2B CPU/QEMU 完整推理和 held-out 安全评测。
