# 2026-11-20 11:28 +0800 — Modular desktop workflow interaction regression fix

## What changed
- The newly created task becomes the selected task and opens its flow immediately.
- Added explicit `steps.startManual` through allowlisted native bridge for research workflows; manual stages never spawn an AI CLI and still require one-shot approval.
- Added native smoke test verifying that a manual step requires approval and records a local event, not a model request.
- Kept the same permission and source-license boundaries as V1.0.

## Verification
- Prior V1.0 Windows workflow succeeded: React build, WPF build, .NET smoke tests, EXE publishing, and offline UI asset check.
- Re-run CI after this small change; Hyper-V GUI acceptance remains pending.

## Next steps
1. Add contract tests for every allowlisted bridge operation and UI event.
2. Extract additional dependency-isolated MIT UI modules with provenance and tests.
3. Move process execution to a least-privilege Windows worker instead of the desktop UI process.
