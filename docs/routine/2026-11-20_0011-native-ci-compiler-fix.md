# 2026-11-20 00:11 +08:00 — Windows native CI compiler fix

## What changed

- Fixed two C# CS0201 compilation errors in `desktop/AIWorkstation.Core/AgentTools.cs` by using explicit `Process.Start(...) is null` checks.
- Kept the fixed allowlisted official CLI integration without changing its permissions or token behavior.

## Verification

- First Windows CI build identified CS0201 on the two process-launch lines; this commit is a targeted source fix. New Windows CI run will independently verify it.

## Next steps

1. Inspect the renewed Windows CI build for WPF/XAML errors and fix any incompatibilities.
2. Verify the self-contained native Windows EXE is produced and uploaded as an artifact.
3. Open and run the EXE inside the Hyper-V guest with standard user privileges.
