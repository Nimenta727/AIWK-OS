# 2026-11-20 14:33 (+08:00) — Fix native Windows Git fixture cleanup

## Changes

- The second native CI run `44687708886` compiled React and WPF and **all core behavior assertions passed**, including Git snapshots, file patches, committed-file inspection, traversal protection and symlink rejection. It failed only when deleting the test fixture: Git for Windows creates read-only object files.
- Updated the temporary-workspace cleanup to clear the Windows ReadOnly attribute on local fixture files (excluding reparse points) before recursive directory removal.
- Production code and permissions are unchanged. The EXE has **not** been verified until the next Windows CI run succeeds.

## Next

1. Re-run Windows smoke tests and confirm cleanup succeeds.
2. Inspect the packaged self-contained EXE and offline UI assets.
3. Run Hyper-V guest GUI acceptance testing and record limitations.


---

## 双语历史编目 / Bilingual historical capsule (2026-11-20)

- 中文：本次档案主题为 **2026-11-20 14:33 (+08:00) — Fix native Windows Git fixture cleanup**，保留此前变更、测试结果、局限和当时的下一步计划。此追加说明不重新验证历史结论。
- English: This dated record concerns **windows git object cleanup**. Its earlier changes, tests, caveats and next steps are preserved. This appended synopsis is not a new verification.
- [历史时间线 / Log index](README.md) · [当前发行 / Current release](../../README.md)
