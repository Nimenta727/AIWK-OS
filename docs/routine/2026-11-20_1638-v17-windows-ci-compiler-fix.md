# 2026-11-20 16:38 (UTC+8) — V1.7 Windows CI 编译修复及目录筛选一致性

## 问题
V1.7 首次 Windows 工作流 44703913456 的 React/TypeScript 编译通过，但 .NET 10 编译失败：`WorkspaceEvolutionService.cs` 的 `HashSet.UnionWith` 调用了不存在的双参数重载（CS1501）。首次编译未生成 EXE，不应宣称通过。

## 修复
- `desktop/AIWorkstation.Core/WorkspaceEvolutionService.cs`：恢复 `UnionWith(evidence.CommittedFiles)` 的单参数调用；Git 重命名另由 `RenamedFiles` 单独解析、显示。
- `desktop/AIWorkstation.Frontend/src/components/ExecutionAtlas.tsx`：路径搜索仍尊重“修改前 / 修改后 / 结构差异”模式，不跨越选择的快照侧显示文件。
- 本文件记录失败原因、涉及文件和下次验收门槛。

## 验证及后续
- 本地复查；Node 逻辑测试 19 项、Python 回归 38 项通过。
- 新 GitHub Windows 工作流必须实际证明 .NET SmokeTests、WPF 编译和 EXE 打包成功；不以静态检查代替。
- 后续在 Hyper-V Guest 检查中文路径、重命名、目录树折叠、两次快照及只读历史 Diff。
