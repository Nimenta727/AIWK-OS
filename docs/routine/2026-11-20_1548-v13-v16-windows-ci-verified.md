# 2026-11-20 15:48 — V1.3–V1.6 Windows CI 验证与剩余任务

## 本次修改
- 更新 docs/ROADMAP.md，逐项列明 V1.3–V1.6 已经编译验证的功能与未完成部分（实机 ConPTY、逐 hunk Git 审批、完整自动编排等）。
- 在 README.md 顶部增加发布验证状态与链接；明确这不是完成安全审计的稳定发行版。
- 增加当前 docs/routine 记录。此提交仅修改文档，不改变功能代码。

## 证据
- 实现提交：930ea00acfe3f3e09689ae6df01b835eb1fdd53b。
- 失败与修复：Actions 44696421362 中 TypeScript 隐式 any 和阶段变量名错误；修复提交 2ba146eaa53805c0dbbde731fe8e49ffb3fc7e32。
- 完整 Windows EXE 构建：Actions 44696677670，已完成且 conclusion=success；Windows x64 发行 artifact id 14610304484。
- Python & Windows checks：Actions 44696677697，conclusion=success。
- 这些结果是 GitHub 执行器环境证据，不等同于在用户 Hyper-V Guest 上的 GUI/安全验收。

## 已知限制
- CLI 仍需用户按官方流程安装和登录，未经授权不自动调用模型。
- DAG 实现依赖编辑、并行隔离和手动确认，不宣称多提供商无人值守自动执行完成。
- Git Worktree 不是 Windows 沙箱；任务事件关联不能单凭时间证明 Agent 编写了代码。
- ConPTY 运行时涉及真实 Windows 句柄、输入法和终端子进程生命周期，需实机测试。

## 下一步
1. 在 Hyper-V Windows 11 Guest 中做 ConPTY 键盘输入、输出中断、终端关闭与长时间压力测试。
2. 给 Git 变更批准实现逐 hunk 的预览、可逆应用和失败回滚，保留人工确认。
3. 对事件账本增加迁移、备份、保留与导出机制。
4. 按官方支持的 CLI 接口增加实际结构化事件捕获与可恢复的受控 DAG 调度，避免转换用户订阅凭据。
5. 每次修改继续在 docs/routine/ 中写明时间、文件、验证、风险及下一步。
