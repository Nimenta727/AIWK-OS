# 2026-11-20 00:15 +08:00 — Fix Windows smoke-test workspace location

## What changed

- The native smoke test now creates its trusted test repository under the CI user's profile on Windows rather than the OS temp directory (`AppData/Local/Temp`).
- Preserved the security guard that intentionally rejects OS and AppData directories.
- Reordered Windows CI steps to compile WPF UI before running smoke tests, so compiler feedback is not blocked by an unrelated test assertion.

## Verification

- Third Windows CI run passed all preceding workflow checks, and failed only when the test attempted to use an AppData folder as a trusted agent workspace.
- New Windows build and test run pending.

## Next steps

1. Ensure WPF XAML compiles successfully on hosted Windows.
2. Verify smoke tests pass on the permitted test folder.
3. Verify the self-contained EXE archive is generated and uploaded.
4. Launch on the user's Hyper-V Windows VM for GUI and CLI interoperability acceptance.
