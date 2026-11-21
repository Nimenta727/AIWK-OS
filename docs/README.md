# Documentation / 文档总导航

> v1.9.0-preview.1 · Engineering Preview. Historical documents retain their original claims; read the current README for active behavior.
>
> **中文：** 历史资料继续保留原始修改、验证和限制。此页面提供中英简介和新版发行入口。
>
> **English:** Historical records remain preserved; this index offers bilingual descriptions and up-to-date release links.

## AIWS OS / AI 虚拟机操作系统
- [内置模型微调与独立评测 / Fine-tuning and held-out evaluation standard](AIWS_MODEL_FINETUNING_STANDARD.md) — 供外部贡献者执行的数据、拒绝率、延迟/RSS、质量门禁、LoRA 与回滚规范
- [Windows → Linux Agent 历史投影 / Migration mapping](AIWS_WINDOWS_TO_LINUX_AGENT_MAPPING.md) — 计划版本、AgentRun、WorkItems、ExecutionRecords 的不可执行受界映射
- [AIWS 小模型与本地推理 / Offline local assistant](AIWS_LOCAL_MODEL.md) — guest-only llama.cpp、模型权限、评测与 LoRA 准备
- [AIWS OS 强制四项验收 / Four priority acceptance gates](AIWS_OS_PRIORITY_GATES.md) — P0 GUI、P0 Linux 统一任务/DAG、P1 NixOS 真正构建与启动、P1 guest-only 权限与恢复
- [模块化系统重构 / Modular AI-native OS](AIWS_MODULAR_OS.md) — NixOS/Debian 镜像适配、共用 React、系统 Agent 和真实开机验证
- [代码智能索引 / Cross-platform code intelligence](AIWS_CODE_INTELLIGENCE.md) — C#/Swift 符号、跨文件引用候选、MSBuild/SwiftPM 依赖与平台 API 证据
- [Windows/macOS 跨平台源码 / Cross-platform authoring](AIWS_CROSS_PLATFORM_AUTHORING.md) — 在 Linux 客户机生成、阅读、编辑 Windows/macOS 源工程；无需专有 SDK
- [AI 原生工具接口 / Agent tool fabric](AIWS_AGENT_TOOL_FABRIC.md) — MCP stdio、代码、浏览器、语言运行与隔离约束 / machine-callable guest tools
- [OS 工程 / OS project](../os/README.md) — Debian Live 镜像、内置开发工具和宿主离线启动 / image build, bundled developer tools, offline-first host launch
- [OS 深度定制蓝图 / OS kernel & isolation blueprint](AIWS_OS_BLUEPRINT.md) — 内核选项、Agent 管理员权限、虚拟机外部安全边界 / kernel profile, privileged agents, external VM boundaries

## 当前版本 / Current release
- [主 README / Main README](../README.md) — 双语安装、使用和安全说明 / bilingual installation, usage and safety
- [发行说明 / Release notes](RELEASE_NOTES_V19.md) — 当前预览内容 / preview changes
- [发行检查 / Release checklist](RELEASE_CHECKLIST.md) — CI 与 Hyper-V 手动验收 / automated versus manual gates
- [内部执行透视 / Internal Observatory](INTERNAL_OBSERVATORY_V19.md) — 调用证据、上下文和 Git 结构 / evidence-linked internal execution
- [安全边界 / Security](SECURITY.md) — 权限与凭据 / permissions and credentials
- [路线图 / Roadmap](ROADMAP.md) — 计划与未完成能力 / future work, not shipped claims

## 设计与版本资料 / Versioned technical notes
- [ARCHITECTURE.md](ARCHITECTURE.md) — 架构与上游参考 / Architecture and upstream references
- [DESKTOP_REBUILD.md](DESKTOP_REBUILD.md) — Windows 原生桌面 / Windows native desktop
- [DEVELOPER_MODULES_V11.md](DEVELOPER_MODULES_V11.md) — Git 工具及权限 / Git tools and permissions
- [EXECUTION_ATLAS_V17.md](EXECUTION_ATLAS_V17.md) — 执行调用与结构演化 / Execution and structural changes
- [EXECUTION_BASE_REVIEW_V07.md](EXECUTION_BASE_REVIEW_V07.md) — 执行持久化与恢复 / Execution persistence and recovery
- [IMPLEMENTATION_V13_V16.md](IMPLEMENTATION_V13_V16.md) — Worktree、ConPTY、事件账本、DAG / Worktrees, ConPTY, ledger, DAG
- [MODULAR_RECOMPOSITION_V1.md](MODULAR_RECOMPOSITION_V1.md) — 独立前端模块重组 / Independent modular front-end
- [PLAN_STUDIO_V171.md](PLAN_STUDIO_V171.md) — Markdown 计划中心 / Markdown Plan Studio
- [PROFESSIONAL_FRONTENDS.md](PROFESSIONAL_FRONTENDS.md) — 旧上游整套前端方案 / Legacy hosted upstream UIs
- [PROJECT_EVIDENCE_V12.md](PROJECT_EVIDENCE_V12.md) — Git 文件证据 / Project/Git evidence
- [REQUEST_TRACE.md](REQUEST_TRACE.md) — 请求追踪与 Token / Request tracing and tokens
- [ROADMAP.md](ROADMAP.md) — 产品规划 / Product roadmap
- [SECURITY.md](SECURITY.md) — 安全边界 / Security boundaries
- [TOKEN_EFFICIENCY_V172.md](TOKEN_EFFICIENCY_V172.md) — 上下文预算与消耗控制 / Context budgets and token optimization
- [UI_STUDIO_V181.md](UI_STUDIO_V181.md) — Studio UI 与交互 / Studio UI and interaction tests
- [UNIFIED_AGENT_CONTROL_PLANE.md](UNIFIED_AGENT_CONTROL_PLANE.md) — 统一 Agent 控制平面 / Unified agent control plane
- [UNIFIED_ORCHESTRATION_V18.md](UNIFIED_ORCHESTRATION_V18.md) — 多 Agent 调度 / Agent orchestration
- [UNIFIED_TASK_IMPLEMENTATION.md](UNIFIED_TASK_IMPLEMENTATION.md) — 统一任务与上下文编译 / Unified tasks and context compilation
- [UPSTREAM_MIGRATION.md](UPSTREAM_MIGRATION.md) — 开源迁移与许可 / Upstream migration and licensing
- [V03_OPERATIONS.md](V03_OPERATIONS.md) — 旧版 Python 原型 / Legacy Python operations

## 历史记录 / Historical records
[完整时间索引 / Complete chronology](routine/README.md) · [GitHub Actions](https://github.com/Nimenta727/Windows-AI-Workstation/actions)

> 本次添加双语导读和索引，**不等于逐句完成所有历史资料全文翻译**。原始记录保持可审计。
> 
> Bilingual abstracts and links are supplied without claiming word-for-word translations of every historical page.

- [AIWS OS unified guest model, persistent agent, system services and kernel candidate pipeline](AIWS_GUEST_AGENT_SYSTEM_KERNEL.md) — 客户机系统整合进展与验收条件
