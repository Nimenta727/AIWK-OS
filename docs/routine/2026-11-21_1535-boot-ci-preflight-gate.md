# 2026-11-21 15:35 — Unblock ISO boot acceptance CI

## Actual evidence
- On SHA `f789c03b`, OS static workflow 44867152142 failed at Shell syntax / Python compile.
- Exact error: `SyntaxError: expected ':'` at installer preflight line 34; the multiline `if` expression lacked parentheses.
- Python & Windows checks succeeded. Debian image/VM boot workflow 44867152211 was still running at inspection; this is **not** evidence of successful firmware boot.

## Changes
- Replace unsafe multiline conditional with `any(item.get(key) for key in (...))`, preserving rejection of existing filesystem/partition signatures.
- Leave disk installation disabled. No host disk writes.
- Update routine index.

## Next
1. Verify Python compile and all OS static tests on the new commit.
2. Collect ISO image build and BIOS/UEFI boot evidence without interrupting the active workflow.
3. Only then advance to disposable qcow2 install/persistence and A/B rollback gates.
