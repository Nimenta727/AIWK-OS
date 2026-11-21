# 2026-11-21 12:01 — 统一 Linux Agent 大结果合法持久化与审计哈希

## 发现与改动
- Linux GuestTaskStore.finished 之前将超过 65536 字符的 JSON 字符串直接切片，这会产生不可解析的 result_json；已完成的任务因此可能在 GUI/Agent 重启后因 JSONDecodeError 无法读取。
- 现在当 UTF-8 字节超过 64KiB 时，以合法 JSON 保存 `{truncated:true,preview:...,originalSha256:...}`；SHA-256 指向**完整原始返回内容**，在审计事件中仅记录 hash 与截断标记，避免拷贝文件正文。
- 未超出 64KiB 的普通结果按 JSON 原样保存。使用 UTF-8 字节作为限额而非不准确的字符数，并避免切割中文多字节字符。
- 回归测试新增 120k 字符级中文结果、已完成状态、合法的预览、原始哈希、一致的审计事件、关闭和重新打开 SQLite 后依然可读等验证。
- 修改：`os/runtime/aiws_tasks.py`、`os/verify/test_tasks.py`、本 routine 及 `docs/routine/README.md`。

## 验证边界
- 改动将在本次 OS 静态合同/Python/ISO QEMU 工作流中验证，CI 真正完成前不标记通过。
- 审计哈希链并非可信计算或针对 guest root 的防篡改保证；极大的原始结果会被截断为用户可见预览而不是全量数据库正文。
- 这不触碰宿主进程、挂载、GPU、内核或虚拟化控制面，写入仅发生在 guest SQLite。

## 下一步
- 持续验证独立 Agent 的跨重启任务与审计恢复、同 UID Unix IPC。
- 继续真实 Qwen3.5-2B 离线 CPU / QEMU 推理验收；修复实际模型兼容性问题。
- Windows UnifiedTaskCore 的计划修订、工件与 AgentRunRecord 语义做兼容迁移测试；尚未完成 1:1 功能对等。
