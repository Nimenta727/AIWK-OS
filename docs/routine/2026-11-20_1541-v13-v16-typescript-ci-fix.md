# 2026-11-20 15:41 — Windows CI TypeScript build corrections
## 变更
- 修复 DAG 模型投影从纯 JS 导入时产生的隐式 any；让 React 节点获得强类型。
- 修复 ProjectExplorer 向 native bridge 传递当前选中阶段标识时使用了未声明变量。
## 文件
- desktop/AIWorkstation.Frontend/src/components/DagCanvas.tsx
- desktop/AIWorkstation.Frontend/src/components/ProjectExplorer.tsx
- docs/routine/2026-11-20_1541-v13-v16-typescript-ci-fix.md
## 验证
- Github Actions 原失败记录：44696421362，13 项 UI 测试通过，tsc 失败。
- 本次依照 tsc 错误修复；需新 Windows CI 证明编译通过，不提前宣称。
## 下一步
- 运行完整 WPF/.NET 构建及实际 Git Worktree smoke tests。
- Windows GUI 实测 ConPTY 键盘、缩放和进程结束后的资源释放。
