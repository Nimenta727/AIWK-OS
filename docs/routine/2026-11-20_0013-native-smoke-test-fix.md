# 2026-11-20 00:13 +08:00 — Core smoke test exception handling

## What changed

- Updated `desktop/AIWorkstation.Core.SmokeTests/Program.cs` so its expected-rejection helper handles both `ArgumentException` and `InvalidOperationException`.
- No core logic changed: blank workflow results remain invalid by design.

## Verification

- Windows CI succeeded in compiling the core library, then exposed an incorrect smoke-test expectation for a blank result. This change addresses that test-only failure. Fresh CI pending.

## Next steps

1. Re-run core smoke tests and compile the Windows WPF frontend in Actions.
2. Verify publish creates `WindowsAIWorkstation.exe` and the artifact is downloadable.
3. Run GUI interactions on the Hyper-V Windows guest.
