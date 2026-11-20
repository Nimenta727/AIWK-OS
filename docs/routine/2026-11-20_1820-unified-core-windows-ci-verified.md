# 2026-11-20 18:20 — V1.7.3 统一任务与模型交接 CI 验收

## 本次操作
已完成统一任务内核、ContextCompiler、ProviderAdapterRegistry 三阶段第一版的 Windows 编译验证。记录源码提交、TypeScript 编译修复、CI 状态、EXE 产物核验及下一步验收计划。这次仅增加验收文档、README/技术说明的状态更新，不改业务代码。

## 已验证内容
- 功能提交 `c5336a2b1293094b7b8fd966e035a7208060559a`：新增 Task Unified 版本模型、计划工件哈希、确定性 HandoffBundle、Claude/Codex/Manual 能力契约和界面操作。
- 编译修复提交 `ab29d9ae8101933a6c05bcef747f40379516afdc`：修复 React 首次加载时 `snapshot` 可能为空的 TS18047；相关修复明细在 `2026-11-20_1815-ui-snapshot-null-guard.md`。
- [Windows native EXE CI #44717741460](https://github.com/Nimenta727/Windows-AI-Workstation/actions/runs/44717741460)：成功，包含 React TypeScript/Vite 编译、WPF .NET 10 编译、Core smoke、win-x64 self-contained EXE 发布。
- [Python & Windows checks #44717741422](https://github.com/Nimenta727/Windows-AI-Workstation/actions/runs/44717741422)：成功。
- 本地：Python unittest **38/38**，Node 前端逻辑测试 **26/26**。
- Actions artifact ID `14619264628`；下载的发行 ZIP 约 60.2 MB；检查发现 `WindowsAIWorkstation.exe` (MZ)、`ui-dist/index.html`，共 9 个 ZIP 目录条目。运行包 SHA256 `424d38ee3756f0d52fc73ca599977f3a9303b62960d6664d40ef44fc06ccdfd2`。

## 未覆盖与风险
- 没有在用户自己的 Windows/Hyper-V VM 中做真实 GUI、账号登录、外部 CLI 运行或权限/隔离验收。
- 无人值守的跨模型 Agent 调度和 CLI 内部请求全量追踪尚未实现；外部 CLI 的 Token 不受本地预算硬限制。
- 本地 `HandoffBundle` 和本地 launch-intent 不是官方模型请求回执，不能据此推断远程真实 Token 数。
- 扩展 DAG 自动运行前，还需 Windows 独立执行 Broker 和 IPC 审核。

## 下一步
1. Hyper-V 实机验证：旧任务迁移、计划版本绑定、切换 Claude/Codex、原生二次确认、上下文检视与 UI 响应。
2. 建立相同项目任务的跨 Agent 交接基准，量化 prompt 重复比例和可用的官方结构化 Token 证据。
3. 为计划版本增加文件哈希漂移警告，避免引用过期计划。
4. 在符合官方 CLI 支持边界和用户审批要求的前提下设计可恢复调度队列；继续遵守每次 GitHub 修改记录 docs/routine 的约束。
