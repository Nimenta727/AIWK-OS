# 文档中心 / Documentation

> AIWK-OS 是**面向程序员的 AI 原生操作系统**（测试版）。这里只放**当前**有效的文档；旧版本资料在 [history/](history/README.md)，每次修改的记录在 [routine/](routine/README.md)。
> 文档里的“已完成”只表示代码与测试，**不等于**真实镜像/模型/固件已验收；每份文档都标明了边界。

## 从这里开始

| 想了解 | 读 |
| --- | --- |
| 系统是什么、怎么用、做到哪一步 | [根 README](../README.md) |
| 目录与模块职责、执行路径 | [CODEBASE_MAP](CODEBASE_MAP.md) |
| 安全模型与没做到的部分 | [SECURITY](SECURITY.md) · [Permission Broker](AIWS_PERMISSION_BROKER.md) |
| 发行说明与发行前检查 | [OS 预览发行说明](RELEASE_NOTES_OS_PREVIEW.md) · [CHANGELOG](../CHANGELOG.md) |
| 第三方组件与许可 | [THIRD_PARTY](THIRD_PARTY.md) · [NOTICE](../NOTICE) |
| 构建镜像 | [OS 工程说明](../os/README.md) · [Debian 构建](../os/debian/README.md) · [AIWS Code](../os/ide/README.md) |

## 设计文档（当前）

| 主题 | 文档 |
| --- | --- |
| AI 原生路线与已定决策 | [AIWS_NATIVE_AI_PLAN](AIWS_NATIVE_AI_PLAN.md) |
| 观察台（首页）与 token 统计 | [AIWS_OBSERVATORY_PLAN](AIWS_OBSERVATORY_PLAN.md) |
| 本地小模型与模型路由 | [AIWS_LOCAL_MODEL](AIWS_LOCAL_MODEL.md) · [AIWS_MODEL_ROUTER](AIWS_MODEL_ROUTER.md) · [微调与评测标准（含数据集 v3）](AIWS_MODEL_FINETUNING_STANDARD.md) |
| 工具审批：AI 启动程序 / 外部工具 | [AIWS_TOOL_APPROVAL](AIWS_TOOL_APPROVAL.md) · [工具能力层](AIWS_AGENT_TOOL_FABRIC.md) |
| 客户机 Agent、系统服务、内核候选 | [AIWS_GUEST_AGENT_SYSTEM_KERNEL](AIWS_GUEST_AGENT_SYSTEM_KERNEL.md) |
| 代码智能与跨平台源码编写（只读原型） | [AIWS_CODE_INTELLIGENCE](AIWS_CODE_INTELLIGENCE.md) · [AIWS_CROSS_PLATFORM_AUTHORING](AIWS_CROSS_PLATFORM_AUTHORING.md) |
| OS 蓝图与阶段门槛 | [AIWS_OS_BLUEPRINT](AIWS_OS_BLUEPRINT.md) · [AIWS_OS_ALPHA_PLAN](AIWS_OS_ALPHA_PLAN.md) · [AIWS_OS_PRODUCTION_GATES](AIWS_OS_PRODUCTION_GATES.md) |
| 旧 Windows 任务历史的受限导入 | [AIWS_WINDOWS_TO_LINUX_AGENT_MAPPING](AIWS_WINDOWS_TO_LINUX_AGENT_MAPPING.md) |

## 历史与记录
- [history/](history/README.md)：旧 Windows 工作台、旧 Python 控制平面、NixOS 实验配方的设计资料与归档（**不再代表当前产品**）。
- [routine/](routine/README.md)：每次修改的时间、内容、验证、已知问题与下一步（按仓库规则持续追加）。
