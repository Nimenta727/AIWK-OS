# 2026-11-20 14:33 (+08:00) — Fix native Windows Git fixture cleanup

## Changes

- The second native CI run `44687708886` compiled React and WPF and **all core behavior assertions passed**, including Git snapshots, file patches, committed-file inspection, traversal protection and symlink rejection. It failed only when deleting the test fixture: Git for Windows creates read-only object files.
- Updated the temporary-workspace cleanup to clear the Windows ReadOnly attribute on local fixture files (excluding reparse points) before recursive directory removal.
- Production code and permissions are unchanged. The EXE has **not** been verified until the next Windows CI run succeeds.

## Next

1. Re-run Windows smoke tests and confirm cleanup succeeds.
2. Inspect the packaged self-contained EXE and offline UI assets.
3. Run Hyper-V guest GUI acceptance testing and record limitations.
