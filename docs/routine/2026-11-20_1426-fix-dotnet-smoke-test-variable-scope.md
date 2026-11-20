# 2026-11-20 14:26 (+08:00) — Fix Windows .NET smoke-test variable scope

## What changed

- GitHub Actions compiled the V1.2 React frontend and WPF host; the .NET smoke-test project failed to compile with CS0841 because the newly added traversal test referenced `projectRoot` before its declaration.
- Changed that assertion to use the already available trusted `workspace` directory. No production Git/Agent code changed.
- This fixes the test harness compiler error; it does not yet confirm runtime test or EXE publishing success.

## Next steps

1. Re-run Windows .NET smoke tests and inspect any runtime errors.
2. Require a successful EXE publish with offline `ui-dist` assets before distribution.
3. Run Hyper-V GUI verification for file tree, Git review and stage checkpoints.
