# 文档中心 / Documentation

> **当前事实优先 / Current status first.** 本索引区分正在维护的工程规范、版本历史资料和开发日志。旧文档的“已完成”陈述仅对其当时版本有效，不应当作当前发行承诺。

## 从这里开始 / Start here

| 主题 | 主要文档 | 内容 |
| --- | --- | --- |
| 产品和安装 | [Root README](../README.md) | Windows 工作台与 Linux OS 的区别、使用方式和限制 |
| 代码结构 | [CODEBASE_MAP](CODEBASE_MAP.md) | 目录职责、入口、数据流、可修改边界 |
| Alpha 0.1 开发门槛 | [ALPHA_PLAN](AIWS_OS_ALPHA_PLAN.md) | M1 安装恢复、M2 Shell、M3 强制隔离、M4 自主 Agent 的分阶段验收 |
| Linux 系统构建 | [OS README](../os/README.md) | Debian 构建、QEMU、NixOS 与验证命令 |
| Windows 版本发布 | [Release checklist](RELEASE_CHECKLIST.md) | 自动与人工验收、发行包要求 |
| 安全与权限 | [SECURITY](SECURITY.md) · [Permission Broker](AIWS_PERMISSION_BROKER.md) | 信任边界、应用层授权、未完成的强制隔离 |
| 当前 OS 验收 | [OS production gates](AIWS_OS_PRODUCTION_GATES.md) | 固件、Shell、权限、模型和真实证据 |
| 开发记录 | [Routine](routine/README.md) | 每次提交的时间、改动、验证和下一步 |
| 旧版技术设计 | [History](HISTORY.md) | 历史版本索引及 Git 保留方式 |

## AIWS OS / Linux 系统工程

- [Guest Agent、系统服务、内核候选](AIWS_GUEST_AGENT_SYSTEM_KERNEL.md) — 持久任务 DAG、systemd 和实验性引导管理。
- [Permission Broker](AIWS_PERMISSION_BROKER.md) — 独立同 UID 决策服务；**不是**内核 MAC。
- [OS production gates](AIWS_OS_PRODUCTION_GATES.md) — ISO BIOS/UEFI、GUI、模型、权限验收。
- [OS priority gates](AIWS_OS_PRIORITY_GATES.md) — 早期 P0/P1 阶段检查；以最新 production gates 为准。
- [Modular OS](AIWS_MODULAR_OS.md) — Debian/NixOS 适配架构。
- [Agent tool fabric](AIWS_AGENT_TOOL_FABRIC.md) — 只读 MCP、Agent/Broker 调用链和工具边界。
- [Local model](AIWS_LOCAL_MODEL.md) — GGUF/llama.cpp 本地推理与受控建议。
- [Fine-tuning standard](AIWS_MODEL_FINETUNING_STANDARD.md) — 数据、LoRA、独立评测、延迟/RSS 与回滚。
- [Windows → Linux mapping](AIWS_WINDOWS_TO_LINUX_AGENT_MAPPING.md) — 历史记录不可执行投影。
- [Code intelligence](AIWS_CODE_INTELLIGENCE.md) · [Cross-platform authoring](AIWS_CROSS_PLATFORM_AUTHORING.md) — C#/Swift 代码阅读和源码工程支持。
- [OS kernel and isolation blueprint](AIWS_OS_BLUEPRINT.md) — 目标设计；**不等于已交付内核**。

## Windows 工作台 / Desktop workstation

- [Desktop rebuild](DESKTOP_REBUILD.md) — WPF/.NET 与 WebView2。
- [Unified Agent control plane](UNIFIED_AGENT_CONTROL_PLANE.md) — Windows Agent 控制层设计。
- [Unified tasks](UNIFIED_TASK_IMPLEMENTATION.md) · [Orchestration](UNIFIED_ORCHESTRATION_V18.md) — 任务、DAG、执行器与上下文。
- [Internal observatory](INTERNAL_OBSERVATORY_V19.md) — 执行证据与 UI 可视化。
- [Release notes](RELEASE_NOTES_V19.md) · [Release checklist](RELEASE_CHECKLIST.md) — v1.9 Windows 预览发行资料。

## 历史、设计草案和审计 / History and evidence

旧版 V0.x/V1.x 技术资料仍可在 [历史导航](HISTORY.md) 找到；它们是**版本快照**，不是当前功能表。每次开发变更的完整证据在 [docs/routine](routine/README.md)，旧 README 和代码可从 Git 提交历史读取。

**English:** Use the current README and OS production gates for present capabilities. Historical versioned documents and dated logs remain available for traceability, but their implementation and acceptance claims are scoped to their original commits.
