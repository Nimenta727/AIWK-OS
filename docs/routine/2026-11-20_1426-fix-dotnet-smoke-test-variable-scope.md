# 2026-11-20 14:26 (+08:00) — Fix Windows .NET smoke-test variable scope

## What changed

- GitHub Actions compiled the V1.2 React frontend and WPF host; the .NET smoke-test project failed to compile with CS0841 because the newly added traversal test referenced `projectRoot` before its declaration.
- Changed that assertion to use the already available trusted `workspace` directory. No production Git/Agent code changed.
- This fixes the test harness compiler error; it does not yet confirm runtime test or EXE publishing success.

## Next steps

1. Re-run Windows .NET smoke tests and inspect any runtime errors.
2. Require a successful EXE publish with offline `ui-dist` assets before distribution.
3. Run Hyper-V GUI verification for file tree, Git review and stage checkpoints.


---

## 双语历史编目 / Bilingual historical capsule (2026-11-20)

- 中文：本次档案主题为 **2026-11-20 14:26 (+08:00) — Fix Windows .NET smoke-test variable scope**，保留此前变更、测试结果、局限和当时的下一步计划。此追加说明不重新验证历史结论。
- English: This dated record concerns **fix dotnet smoke test variable scope**. Its earlier changes, tests, caveats and next steps are preserved. This appended synopsis is not a new verification.
- [历史时间线 / Log index](README.md) · [当前发行 / Current release](../../README.md)
