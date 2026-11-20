# 2026-11-21 01:20 — Persistent AIWS guest task DAG, approvals, audit

## 本次代码变更
- 新增 os/runtime/aiws_tasks.py，以 guest-only 普通用户私有的 SQLite 数据库存储任务、DAG 阶段、依赖、审批和可审计事件哈希链。
- DAG 限制 32 个阶段，拒绝重复 key、循环依赖、未知依赖和 host 工具；默认只读操作可排队，file.replace 等 guest 文件修改必须明确审核。
- 状态包括 pending/queued/running/completed/failed/interrupted；重启后曾排队或运行的阶段标记为 interrupted，避免假装已完成；阻止重复 dispatch。
- 新增 os/verify/test_tasks.py，覆盖循环/非法工具拒绝、依赖阻塞、审批、审计哈希和跨进程恢复。
- 本模块还没有绑定 HTTP 控制器 UI；下一提交做 Controller 运行器、API 路由与测试，随后移入镜像。

## 验证与限制
需要本次 GitHub OS 静态测试实际通过。当前库只保存本地任务计划与进度，暂不声称覆盖 Windows 的所有高级 DAG、执行器协议与审批语义；没有云端推理或宿主操作权限。SQLite 哈希链用于检测普通记录篡改，不是防止 guest root 篡改的不可变审计。

## 下一步
接入 AIWS workbench API、guest toolplane、项目/阶段 UI、离线模型建议层、真实 GUI 点击验收。
