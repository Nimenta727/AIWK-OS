# 2026-11-21 11:55 — Atomic SQLite transition and audit receipts

## Changes
- In the persistent guest DAG, state mutations and their audit receipts were separate auto-commit writes. A disk failure between them could leave an approved or dispatched stage with no corresponding audit record. Introduce a BEGIN IMMEDIATE transaction wrapper with full audit-chain prevalidation, commit on success and rollback on failure.
- Wrap approval, dispatch, start, finish, interrupted restart recovery, and model provenance event updates. Task creation already had a single atomic transaction and remains unchanged.
- Add a fault-injection unit test in test_tasks.py for audit write failure in approval/dispatch/start. Confirm the stage state is rolled back, chain remains valid and retry is possible.

## Files
os/runtime/aiws_tasks.py, os/verify/test_tasks.py, this routine.

## Validation and next steps
Requires Python/Windows, OS static and QEMU guest lifecycle CI verification. SQLite transaction atomicity is not an externally signed audit and cannot protect from a malicious guest root. Real kernel boot A/B and local 2B inference still require independent positive receipts.
