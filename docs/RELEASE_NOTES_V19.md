# AIWS v1.9.0-preview.1 — Release Notes / 发行说明

**Status / 状态：Engineering Preview · 工程预发布，不是安全审计后的稳定版。**

## 中文
本次发行重点是**内部执行可视化与中英文资料整合**，保留 V1.8.1 Studio 的现有工作流、任务、Git、计划和终端模块。

**新增：**
- 内部执行透视：一个任务中的 Agent 阶段拓扑、五段调用证据、上下文来源、用量、目录级 Git 变化及代码 Diff。
- 中/英语言切换：主导航与新的内部透视，帮助页与旧专业面板部分仍使用中文。
- README 双语重构、技术文档中英导读、历史开发记录双语编目、GitHub Release 预发布流程与 SHA-256 完整性校验。
- 回归范围扩展：本地数据投影单元测试及 Windows Edge 交互测试。

**未完成或不保证：** AIWS 不直接观察官方 CLI 隐藏的全部请求/Token；Agent 自动执行仍需符合官方能力与用户授权；Hyper-V 中 ConPTY/IME/ACL 未经过真人测试；此版本未进行代码签名。

## English
This preview strengthens **internal observability** and reorganizes the documentation into a bilingual, navigable release set. Existing V1.8.1 Studio workflows, Git inspection, Plan Studio and Windows terminal functionality remain available.

**Added:** a task-level Internal Observatory linking stage topology, five evidence phases, provenance-aware handoffs, imported usage, directory-level Git changes and file diffs; an English/Chinese switch for the primary shell and new surface; bilingual README, indexed historical logs, a reproducible GitHub release workflow and SHA-256 checksum artifacts.

**Not yet guaranteed:** inaccessible provider-internal requests or usage, fully unattended model execution, complete translation of every older specialist screen, real Hyper-V GUI / ConPTY / ACL validation, or executable signing.

## Upgrade / 升级
1. Back up / 先备份 `%LOCALAPPDATA%\WindowsAIWorkstation`.
2. Download the **whole ZIP**, verify its `.sha256` and extract alongside `ui-dist/`.
3. Run as an unprivileged Windows user in a trusted project or a disposable VM.
4. Verify a task, local Git changes, the new observability page, CLI permissions and terminal behavior. Do not copy provider authentication files into this app.
