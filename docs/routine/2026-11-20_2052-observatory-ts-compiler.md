# 2026-11-20 20:52 — Observatory TypeScript CI correction / 透视页编译修复

## 中文
Windows CI 首次运行在 React TypeScript 检查中报告 `InternalObservatory.tsx` 中动态 Git 文件列表回调参数隐式 any（TS7006），导致后续 WPF / EXE 步骤未运行。现为该文件变更行指定明确的路径及状态类型；只修复类型契约，未放宽运行时 Git 操作权限。

## English
The first Windows CI run stopped at TypeScript error TS7006 (untyped dynamically projected Git file callback). The callback now declares the file path/change shape; this does not change the read-only Git security boundary.

## 验证 / Verification
- 失败证据：Windows Actions #44738702243, TypeScript stage.
- 修复后的 Windows CI 编译与 Edge 点击结果仍待新的工作流运行确认。

## 下一步 / Next
Finish bilingual historical indexing, rerun the full Windows CI pipeline, then publish a checksummed prerelease only after all automated gates pass. Hyper-V GUI remains pending.
