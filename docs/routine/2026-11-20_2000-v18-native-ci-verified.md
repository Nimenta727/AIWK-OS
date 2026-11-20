# 2026-11-20 20:00 — V1.8 统一调度与总控台 Windows CI 验收

## 本轮修改
- 更新 README、ROADMAP、UNIFIED_ORCHESTRATION_V18：补充真实 Windows CI 和 ZIP 完整性证据；所有未完成能力仍标注限制。
- 新增此 docs/routine 验证记录。本轮仅文档修改，不更改运行时代码。

## 测试与产物
- 最终代码提交 `cf94146da43e09cc9dc083ffd16f4bb1c29d6082`。
- Windows Native EXE: [#44729416838](https://github.com/Nimenta727/Windows-AI-Workstation/actions/runs/44729416838) 成功。React 29/29，.NET core smoke，WPF 编译，win-x64 离线打包成功。
- Python/Windows: [#44729416839](https://github.com/Nimenta727/Windows-AI-Workstation/actions/runs/44729416839) 成功；Python 回归 38/38。
- 真实下载包验证 WindowsAIWorkstation.exe 与 ui-dist/index.html 存在；内层 ZIP SHA256 `7d65f301b7ae33faaebe0eae5a1d2061104f8cadcdacca3e18c943c82629be0e`。
- 之前 TS 空快照与 C# 重复测试声明失败均已通过独立带日志的代码提交修复；原始失败运行保留。

## 限制
- 没有用户 Hyper-V VM GUI/ACL 运行验收，Windows CI 不构成该证据。
- 队列是用户监督模式，不自动调用供应商 CLI；Worktree 不构成系统沙箱；正式独立 Broker、安装器签名、更新回滚尚未完成。

## 下一步
1. 在非管理员 Windows VM 使用 `scripts/Test-HyperVAcceptance.ps1` 与隔离测试仓库验收启动、ConPTY、审批/排队/中断、Git 和计划联动。
2. 优先完善最小权限 Windows Worker、受验证 IPC、一次性能力授予、进程取消和故障恢复。
3. 只在官方接口允许的情况下增加受控后台 Provider 适配器；升级链路加入数据迁移/签名/恢复演练。
4. 继续每次 GitHub 修改均有 docs/routine 时间记录。
