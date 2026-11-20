# Windows AI Workstation V0.7 — Execution Base Code Review

Review date: **2026-11-20 (UTC)**  
Baseline: `main` commit `3754e963ecbac4af84c3f0a46b5c012bcd8db614` (V0.6)  
Scope: native WPF/.NET core, task persistence, stage/approval state, CLI launch, workspace guard, imported usage accounting and smoke tests. The legacy Python/Web prototype was regression-tested but **not** redesigned in this round.

## Summary

This is a reliability and security hardening pass, not a feature-completeness audit. V0.6 was a functional local UI but it conflated a few fallible local actions with durable execution state. The key design invariant in V0.7 is:

> **No external agent launch before a valid workspace, current approval, clipboard preparation and persisted intent. No automatic restart of an uncertain external process.**

The app is still an *orchestrator for official interactive CLIs*, **not** a sandboxed unattended AI execution engine and **not** a provider network interceptor.

## Findings and remediation

| ID | Severity | Finding in V0.6 | V0.7 remediation | Proof |
|---|---|---|---|---|
| EX-01 | P0 | `TaskRepository.Save` used backup copy + replacement without validating backup contents, and the UI had no process-wide single writer. Two windows could overwrite each other's task history. | Added `WorkspaceLease` OS file-sharing exclusion, startup handling, validated staged writes and explicit `.bak` restore. | Duplicate lease / atomic persistence / corrupt primary tests. |
| EX-02 | P0 | `MainWindow.StartAgent_Click` marked a step Running and saved it before `Clipboard.SetText`. Clipboard failure left a phantom active stage; a failed post-launch save could be mistaken for a failed launch. | Introduced `StageLaunchCoordinator` with prepare/commit boundary, rollback on pre-launch save failure and separate post-launch persistence failure handling. | Clipboard and injected disk failure tests. |
| EX-03 | P1 | Persisted Running steps were not distinguished from verified running CLI sessions after application restart. | Added `Interrupted` state, startup conversion and explicit Retry; approval is consumed on start and reset on retry. Never auto-launch on restart. | Interrupted recovery and one-shot approval tests. |
| EX-04 | P1 | The workspace check accepted a user-profile root, network shares and linked paths; relative PATH directories could resolve into attacker-controlled checkouts. | Deny root/home/OS/appdata/network workspaces and directory reparse points; ignore relative PATH entries when locating CLI shims. | Root/home/reparse/PATH tests; Windows runtime validation pending. |
| EX-05 | P1 | Invalid JSON could be confused with an empty store, and an existing `.bak` was not exposed for a user-approved recovery workflow. | Validate task IDs/state and JSON before replacement; refuse silent overwrite when primary is corrupt/missing; preserve a forensic copy for explicit restore. | Corrupt, missing and duplicate-ID recovery tests. |
| EX-06 | P2 | Imported token telemetry could accept impossible cached-token ratios or huge values, confusing the request-flow dashboard. | Added provider-specific sanity caps and cached input consistency checks; keep real/estimated/unknown sources separate. | Rejection tests for forged telemetry. |
| EX-07 | P2 | UI event handlers mixed validation, persistence and external effects. | Extracted lease, durable repository logic and stage preparation coordinator into `.Core`; keep WPF UI primarily responsible for user consent and rendering. | Native core smoke tests. |

## Architectural boundaries after the repair

```text
WPF App (presentation + explicit human approval)
    -> WorkspaceLease (exclusive local writer)
    -> WorkflowEngine (preconditions, one-shot approval, recovery)
    -> StageLaunchCoordinator (clipboard -> durable intent; rollback on failure)
    -> TaskRepository (validated JSON -> durable staging -> .bak)
    -> AgentTools (allowlisted official CLI discovery and interactive launch)
    -> RequestTrace / CallFlow (metadata + explicitly imported usage, never invented usage)
```

The order of external side effects matters. Once the CLI is started, a subsequent *trace save failure* must **not** cause the UI to claim the process never ran, nor re-execute the task. A restart converts the persisted Running step to Interrupted until the operator checks the external terminal. Workspace validation is a *preflight check*, not an OS sandbox; the spawned CLI inherits the logged-in Windows user's permissions.

## Validation

- Legacy Python regression suite: `python -m unittest discover -s tests -v` — **38 passed locally**.
- Native `.NET` smoke tests: expanded to cover lease contention, corruption recovery, launch ordering, interrupted state, one-shot approval, and token validation. **Windows CI result is the authority for compilation and smoke tests**; don't claim a successful EXE build before the corresponding Actions run has completed.
- No test in this repository proves the ability to introspect Claude/Codex private model requests or guarantees an actual token cap.

## Remaining risks / deferred decisions

1. **CLI permissions:** A native executable inherits the Windows user token; preflight path restrictions do not make it sandboxed. Use an isolated Windows account/Hyper-V checkpoints; add a policy-enforced Windows execution broker before unattended automation.
2. **Persistence scalability:** JSON+backup is appropriate for single-user MVP, not multi-machine concurrency or heavy task volume. Evaluate transactional SQLite with schema migration and recovery tooling.
3. **Agent lifecycle:** CLI launch is observable, but process liveness, session output, and remote model usage are *not* fully integrated. An official supported event/protocol adapter must be built separately.
4. **WPF event handlers:** Longer-term migrate to MVVM/use-case services and add UI automation tests, without silently changing the subscription model.
5. **Privacy:** `.bak` and forensic `.corrupt-*.json` snapshots contain task text; keep them under user-private AppData and document retention/deletion controls.
6. **External dependencies:** Keep third-party tools separate and honor their licenses and providers' authentication rules. No unreviewed AGPL source transplant into the native application.

## Windows acceptance test

1. On a Hyper-V snapshot, run the CI-produced Windows EXE **as a normal Windows user**.
2. Open two instances: the second must show a clear single-writer error, and the first keeps its tasks.
3. Create a task, approve a stage and begin only after valid project directory and CLI preflight. Temporarily make the clipboard unavailable or database unwritable; no accidental CLI should start.
4. Start a stage, close the workbench, reopen: see **Interrupted**, not automatic CLI launch; check the external CLI before using Retry.
5. Corrupt `tasks.json` on a disposable test VM: confirm the user is offered backup restore, original corrupt file is preserved, and a valid restored snapshot loads.
6. Import malformed token logs: reject improbable cached input; unknown measurements remain labeled unknown.

## Release/rollback

The core modifications are additive and continue reading the existing string-enum JSON model. Keep a separate copy of `%LOCALAPPDATA%\WindowsAIWorkstation\tasks.json` and `.bak` before first V0.7 launch. Roll back the EXE through the V0.6 artifact if needed; do **not** automatically overwrite data from the newer release with an older version.
