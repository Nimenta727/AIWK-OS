# AIWS V1.7.3 — Unified Task Core, Context Compiler, Provider Adapters

Date: 2026-11-20. Scope: **the first three phases** of the unified Agent architecture. This implements a local Windows task control plane; it does **not** implement autonomous cross-provider scheduling or a provider token proxy.

## User-visible workflow

1. Create one task (default **lean**: one Codex stage plus manual acceptance) in a trusted local workspace.
2. Under **可视化工作流 → 统一任务档案**, edit the task-level goal and acceptance criteria. These remain attached to the same task ID through model switches.
3. In **AI 计划中心**, open a recognized local Markdown plan in the **task main directory** and choose **绑定此计划版本**. AIWS reads the validated file and stores a relative path and SHA-256, not the Markdown body. New file content results in a separate revision, and duplicate linking does not create a duplicate revision. Worktree plan reading remains available but is not silently linked to a different repository root.
4. Select a **Pending** workflow step. Inspect **当前执行器** and switch Claude Code ↔ Codex ↔ Manual. The existing stage ID and dependencies remain; any previous approval is revoked. Already started or interrupted stages cannot switch in place.
5. Expand **结构化交接包** to see provenance by goal, instructions, plan hash, stage-result references and bounded handoff excerpts. Opening the *full draft* requires a separate click; the summary endpoint does not return the entire prompt.
6. Explicitly approve/launch the installed official CLI as before. The same deterministic `ContextCompiler` output is used by budget preflight, preview and clipboard delivery. CLI launch remains user-confirmed and is **not** a model-call receipt.

## Stage A — Unified task model and safe migration

New `UnifiedTaskState` on each existing `WorkTask` (schemaVersion=1):

- `Goal`, `AcceptanceCriteria`: AIWS-owned intent, not dependent on a chat provider.
- `PlanRevision`: workspace-relative path, SHA-256, revision ID and link time. No source body persisted.
- `UnifiedWorkItem`: ID **equal to existing WorkflowStep.Id**, stage status, executor and dependencies projected from the canonical workflow state. No second scheduler or competing status flag.
- `AgentRunRecord`: one record per `WorkflowStep.RunId` attempt; adapter ID, local status and `local-intent` evidence. This does not prove a provider received a prompt.
- `TaskArtifactRef`: content hash for linked plans or completed stage results, and a stable stage/path reference; no duplicate model text.

`TaskRepository` reconciles missing legacy fields in memory when loading. Its existing atomic JSON replacement, `.bak`, single-writer lease and explicit corruption recovery remain. Existing task/step/run IDs are retained. Corrupt schema versions, excessive counts, unsafe plan paths and invalid hashes are rejected. A subsequent validated save persists the new fields; the old file is not silently discarded. Any failed controller mutation rolls back the unified record and the authoritative stage fields.

## Stage B — ContextCompiler and deterministic handoff protocol

`ContextCompiler.Compile(task, step)` emits a typed `HandoffBundle` (v1):

- `TaskId`, `StageId`, `AdapterId`, fingerprint, local approximate tokens, sent/saved character counts.
- `Manifest`: each included/omitted source has kind, reference, hash, included flag and provenance.
- `Prompt`: deterministic local handoff text, preserving full current user stage instructions, total task goal, acceptance criteria, at most 3 current plan references, up to 6 known stage-result artifact references and at most 2 directly dependent completed results, each capped at 1200 characters.
- The prompt explicitly identifies earlier Agent output as untrusted and includes the `docs/routine` rule and project execution boundary.

The existing `HandoffBuilder` is now a compatibility wrapper around the compiler. Therefore `ContextBudgetPolicy`, `ContextInspector`, and `StageLaunchCoordinator` use **the same handoff bytes**. No second summarization-model call, no automatic plan-file/body/source reads, no full chat transcript and no automatic model request. Estimated tokens are never presented as actual provider billing metrics.

A plan reference can become stale when its file changes; the SHA is the provenance of the *linked version*, not a guarantee the referenced path still contains those bytes. The user must re-link the updated version when needed. Cross-Agent handoff cannot eliminate provider-internal system prompts or file scans in separately operated official CLIs.

## Stage C — Explicit provider capabilities and switching

`ProviderAdapterRegistry` describes three executors: `claude-cli`, `codex-cli`, `manual`. Each declares installation availability, whether native user launch is required, Worktree support, ability to import structured usage evidence and whether unattended execution/internal request visibility is genuinely supported. In this integration **none claims unattended execution or full request observation**.

`WorkstationController.SwitchAgent` is an allowlisted operation for never-started Pending stages. It does not alter the task, work-item ID, plan versions, dependency graph or existing artifacts. Switching invalidates prior approval and any saved prompt fingerprint; assigning a model executor requires new approval. `AgentTools.LaunchInteractive` still starts separately installed official tools after native Windows confirmation and workspace validation. Login/subscription credentials stay in their official stores.

## UI and native bridge

- `tasks.setBrief`: explicit task goal/acceptance editor, bounded to 6000 characters each, blocked while a stage runs.
- `plans.link`: workspace-validated plan reference, only from the task main project.
- `steps.switchAgent`: Pending-only switch; controller enforces it, not just React.
- `providers.capabilities`: read-only provider capability list.
- `context.bundle`: manifest and token estimate *without prompt body*.
- `context.bundle.preview`: explicit reveal of the local text with existing ContextInspector limits.

All messages stay behind `https://aiws.local/` WebView2 origin allowlisting. No general shell/Git-push/model-inference RPC has been added.

## Testing and acceptance

Additive .NET smoke assertions include:

- Old JSON without `Unified` reconciles with unchanged stage IDs, validates and round-trips.
- Plan linking is idempotent by path+hash and stores no Markdown body; invalid paths remain rejected by PlanWorkspaceService.
- Context compiler is deterministic; preflight and copied prompt are identical; provenance is hash-referenced, not fabricated; old-result trimming still works.
- Switching a Pending executor revokes approval, retains work-item identity, and a running executor cannot switch.
- A fake local launch callback (does not contact providers) produces `local-intent` run metadata and completed-result artifact hashes, surviving restart.
- Existing 38 Python tests and frontend Node tests remain; Windows CI compiles the WPF EXE and runs .NET smoke tests.

**Unverified unless separately recorded:** Hyper-V GUI run, actual Claude/Codex account login, provider private internal calls, system-level sandboxing, full orchestration/retry, automatic plan extraction from a provider account, end-to-end model call/token savings percentages. Passing Windows CI is not equivalent to real VM GUI acceptance.

## Next phase

1. Implement an opt-in **capability-aware but user-controlled** orchestration queue, only using provider-supported APIs.
2. Add conflict detection when a linked plan's on-disk hash diverges from its recorded revision (no automatic prompt upload).
3. Version/compact the run and artifact history with explicit archival rather than silent deletion; test frequent retries and interrupted interactive CLIs.
4. Enhance local context selection with file/commit references, traceable dependency decisions and a measured task benchmark. Do not add a summarizer-model call by default.
5. Add real Hyper-V GUI acceptance and a least-privilege Windows broker before enabling more automated write actions.
