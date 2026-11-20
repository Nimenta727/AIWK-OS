# Request Trace V0.6 — interactive evidence-based call flow

## What a request looks like

1. `task.created` — plan created locally (zero model calls).
2. `stage.approved` — user permits the step; a permission grant is not a model call.
3. `prompt.prepared` / `prompt.reused` — optimized text copied locally; duplicates are detected using a SHA-256 hash. No model call is made.
4. `stage.started` — official interactive CLI is launched, **but actual model request timing and hidden exchanges are not observable from AIWS**.
5. Optional `trace.imported` — user imports a structured usage file from the official CLI. Only numbers and event totals are retained. An import fingerprint prevents double-counting.
6. `stage.completed` — user verifies the result and records it, not necessarily the provider's completion time.

## Usage origins and semantics

- **Codex**: `codex exec --json` yields JSONL; `turn.completed.usage` contains input, cached input, and output token counts. Multiple turns are added; repeated identical imports are ignored. This is an **optional explicit import**, not unattended execution.
- **Claude Code**: structured `result.usage` is imported as the last aggregate record; streaming intermediate assistant usage is deliberately ignored to avoid double-counting. Normalized input includes cache-read and cache-create tokens when provided, because Claude's uncached input excludes them.
- Missing or unsupported usage is **unknown**, never 0. Different formats may expose different data. No subscription balance or pricing is implied.

## Context reduction

- Only the 2 most recently completed steps are included as evidence, up to 1,200 chars each. Older steps are referred to but not copied; duplicates are omitted.
- The user's current stage instruction is **never silently shortened**.
- Estimate display uses a mixed script character heuristic, not a tokenizer, so can be far from actual model usage. CLI system prompts, tool outputs, hidden reasoning and cache policies are not measurable in this preview.
- Automatic deduplication of provider requests **is not implemented**; the duplicate marker flags redundant clipboard preparation only.

## Security boundaries

- Never parse private Claude/Codex credential stores or scrape desktop app internals.
- Import is explicitly initiated from a user-selected JSONL/JSON file, max 5 MB or 20,000 lines.
- Raw chat content, shell command arguments, and original logs are not persisted. Metadata stays in the local tasks.json; protect it as project activity information.
- Avoid importing arbitrary untrusted logs into a privileged process. This importer is read-only and has bounded input, but has not received a third-party security audit.

## Planned V0.6

1. Supported streaming provider adapters with explicit authorization and real-time progress.
2. Per-task budgets and enforceable stop controls *where the official interface supports them*; avoid pretending a soft estimate is a hard budget.
3. Timeline UI details, exportable redacted summaries, and side-by-side efficiency comparisons.
4. Windows guest acceptance testing and signed installer pipeline.


## V0.6 visual call-flow canvas

Every workflow stage renders an independently inspectable row:

1. **Routing:** a selected, local agent assignment, not a model-selected route.
2. **Context:** locally generated handoff. Estimated tokens are a rough heuristic and do not equal provider-billed tokens; copied prompts can be flagged as duplicates.
3. **Launcher:** launch events distinguish `stage.started` from `cli.launched` and `cli.launch_failed`. Historical V0.5 tasks with only `stage.started` are rendered as unverified.
4. **Provider / tools:** unknown unless a user imports supported structured events. Codex `turn.completed` totals are per *turn*, not proof of an individual API request; Claude `result.usage` is a terminal aggregate and not a per-call trace.
5. **Handoff:** user-completed result, and optional duration of the *workflow stage*, not the latency of model requests.

The trace page provides per-node evidence inspector, a metadata-only timeline, a summary of known/unknown token usage, imported turn/tool event chips, and a redacted JSON export.

### Token-reduction protections

- On an identical handoff after prior copying, launching the interactive CLI requires a second explicit user confirmation. This is a duplicate *prompt* warning, not verification of duplicate inference.
- Before launch, estimated handoff sizes exceeding 3,500 approximate tokens trigger a confirmation. This is advisory, not a hard model budget or request interceptor.
- The handoff builder still retains the complete current instruction and two bounded prior-result excerpts. Duplicate completed results are omitted.

### Import and provenance

Imported user-supplied JSON/JSONL is untrusted. The app does **not** authenticate the producer or prove its token totals match a billing dashboard. Structured log parsing stores at most 60 normalized provider metadata entries per imported phase, with event order but no prompt contents, responses, commands, arguments, filenames, or API credentials. Tool started/completed entries are **event records**, not unique tool invocation counts. The app never uses captured credentials to reproduce calls.

The redacted export omits workspaces, task titles, stage instructions, outputs, prompt fingerprints, and full trace summaries; it includes only controlled categorical labels and usage figures. Treat even these activity metrics as local project metadata.

### Not yet implemented

- Live direct visibility into every internal model/API call of interactive Claude Code or Codex sessions.
- Exact per-request cost, subscription balance, true hard budget caps or automatic response collection from the interactive CLIs.
- Unattended cross-provider subscription credential proxying.
- GUI acceptance testing in the user's specific Hyper-V guest.
