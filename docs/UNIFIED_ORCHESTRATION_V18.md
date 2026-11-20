# AIWS: Unified Orchestration / Mission Control / Reliability (V1.8 preview)

> 2026-11-20. Implementation of phases **4, 5 and selected phase-6 safeguards** on top of V1.7.3. A Windows build passing CI does **not** mean a signed V2.0 release or a completed Hyper-V GUI / ACL / penetration test.

## Product objective

**One durable task, multiple replaceable model executors.** The user should not repeatedly copy task plans, Git evidence, context and approvals across unrelated model chats. AIWS owns the task, DAG, artifacts and handoffs. Native CLI providers still own their official authentication and interactive sessions; no subscription tokens are proxied.

## Phase 4 — restart-safe human-supervised Agent scheduler

`AgentScheduler` is a deterministic planner/queue over the existing `WorkflowStep` state, not a second source of truth. It computes readiness from graph dependencies, approvals, local budget, installed provider capabilities, recommended parallel capacity and Worktree isolation. It never invokes an LLM to make this decision.

**State categories:** ready / queued / approval / waiting / capacity / isolation / unavailable / budget / running / completed / interrupted / failed. Readiness is recalculated whenever the UI requests an updated plan. Missing provider capability is reported as unavailable, and an installed alternative can be suggested, **never silently substituted**.

`DispatchRequest` persists ticket ID, stage ID, chosen provider ID, local handoff fingerprint, status (queued/consumed/cancelled), and timestamps. It stores **no prompt, secret, context body or tool command**. A ticket is not a permission grant: the WPF host still requests an explicit native user confirmation before launching an external CLI. The queue does not automatically start agents, re-run failed stages, merge branches or publish GitHub content.

A changed task goal, plan version, provider, prompt budget, DAG structure or Worktree invalidates queued tickets. User-initiated cancellation is idempotent at the workflow level and never alters Git. An external CLI launch consumes an eligible ticket after the host's explicit launch action; a failed start marks the stage failed and requires reconciliation. The existing `WorkflowEngine.MarkInterrupted` prevents automatic replay after process restart.

**Concurrency note:** The recommended active-stage count (1–4) affects scheduler suggestions. It is **not** a process/OS semaphore. `WorkflowEngine.EnsureStartable` separately enforces distinct Worktrees for truly parallel running stages.

## Phase 5 — one visual mission console

`MissionControl.tsx` projects existing task, plan, provider, Git, event and usage evidence into one page. Operators see stage progress, next actionable step, queue/approval, local prompt estimate, plan versions, current Git checkpoint status and privacy-safe diagnostics. Detailed call- and project-structure views reuse the existing Execution Atlas, loaded only after explicit expansion. Navigation links open the full plan and file review without creating another task.

These are **local-only projections**: viewing the page never triggers provider calls or imports raw model conversations. A pending ticket does not indicate that a remote request happened. Unknown token usage remains unknown; worktree snapshots cannot prove AI authorship by themselves.

## Phase 6 — stability and security safeguards introduced

- The native WebView2 bridge serializes potentially mutating actions, including external launch, local Git Worktree creation, approval, queue changes and terminal writes; unknown commands remain rejected.
- The frontend limits concurrent pending requests to 64 and provides a bounded timeout **only for known read-only queries**. It never automatically retries a mutation or process launch.
- Task-store changes remain under the existing exclusive `WorkspaceLease`, validated atomic JSON replacement and backup. The new scheduler fields are additive, bounded and validated on load; older JSON without them can be reconciled.
- `WorkstationDiagnostics` offers a local health summary (counts only) and an **explicitly user-triggered redacted JSON export**. It excludes prompts, task titles, workspace paths, stage results, file contents, terminal output and login data.
- The `scripts/Test-HyperVAcceptance.ps1` preflight reads the extracted distribution and machine capabilities **without running the EXE or modifying the system**. It distinguishes optional CLI presence and Authenticode signature from actual GUI acceptance.
- A Git Worktree is not an OS sandbox; terminal/official CLIs inherit Windows account privileges. Use a dedicated non-admin Hyper-V VM. External network publishing and system edits remain outside automatic scheduling.

## API/State additions

| Feature | Native bridge action | Data effect |
| --- | --- | --- |
| Compute dispatch state | `scheduler.plan` | Read-only pure local projection |
| Add to local queue | `scheduler.queue` | Persist fingerprint-only DispatchRequest; no model request |
| Cancel ticket | `scheduler.cancel` | Mark pending ticket cancelled; no Git operation |
| Concurrency policy | `scheduler.parallel` | Save suggested active stage count (1–4) |
| Local runtime health | `diagnostics.health` | Read-only counts, backup present flag |
| Export redacted health | `diagnostics.export` | User picks local JSON destination; no automatic upload |
| Launch provider | Existing `steps.launch` | Still requires user approval, prompt budget gate and native confirmation |

No new subscription/OAuth, arbitrary shell RPC, model API gateway, system elevation or automatic Git push endpoint was added.

## Acceptance criteria and evidence

1. Native smoke tests: approval required; enqueue/duplicate protection; queue survives restart; explicit cancellation; task-brief edits revoke obsolete tickets; successful explicit launch consumes ticket; running stage cannot be replayed; restart marks unfinished stages interrupted; export strips secret title, goal and workspace paths.
2. Frontend Node tests: deterministic derived completion, unknown token evidence, queue selection and absence of phantom completion. Legacy Python tests remain unchanged.
3. Windows CI: Node/TypeScript build, WPF/.NET compile and smoke tests, self-contained x64 EXE+ui-dist packaging.
4. **Still pending:** real Hyper-V GUI tests (IME, terminal, DPI, Windows ACLs and process lifecycle), complete independent broker/sandbox, signed installer and update/rollback testing, verified structured unattended provider adapters where officially supported, durable background job scheduling and automatic multi-model handoff.

## Near-term follow-up backlog

- **P0:** After CI, run the VM preflight script and visually verify queue/confirm/cancel/restart with a disposable trusted Git project.
- **P0:** Formalize a least-privilege Windows worker with authenticated IPC and one-shot capability grants. Do this before any autonomous tool execution.
- **P0:** Investigate official supported noninteractive CLI event streams and legal authentication contracts; implement unattended dispatch only where supported, with bounded process cancellation and offline test fixtures.
- **P1:** Merge UI status projections through an append-only event migration, long-lived job registry and explicit retry audit, without automatic side-effect replay.
- **P1:** Security review, disk-corruption recovery exercises, signed installer, upgrade migration and release health telemetry with consent/privacy controls.

## Source ownership

All new scheduler, mission control and diagnostic code is AIWS-owned. Existing adapted T3 Code MIT presentation controls remain attributed at `third_party/t3code/NOTICE.md`; no Kandev AGPL source or upstream provider secrets have been imported.
