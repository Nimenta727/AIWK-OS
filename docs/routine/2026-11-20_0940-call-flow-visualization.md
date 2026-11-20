# 2026-11-20 09:40 +0800 — Native request call-flow visualization (V0.6)

## What changed

- Developed an evidence-driven, five-node-per-stage call-flow graph (route, context, CLI launch, provider statistics, handoff) without scraping provider sessions or credentials.
- Redesigned the existing native WPF request-trace page into an interactive warm-white flow canvas and added a right-side node inspector with status, provenance, time and usage information.
- Added bounded, privacy-filtered provider event summaries for user-imported Codex JSONL turns and tool events, and Claude terminal aggregates.
- Added duplicate handoff and high estimated-context warnings before launching official interactive CLI tools, plus successful/failed process-launch events distinct from model calls.
- Added an explicit JSON export of redacted metadata and core smoke tests validating unknown usage, event provenance, safe output and restart persistence.
- Updated usage disclaimers and user documentation.

## Files changed

- `desktop/AIWorkstation.Core/CallFlow.cs` (new)
- `desktop/AIWorkstation.Core/Models.cs`
- `desktop/AIWorkstation.Core/RequestTrace.cs`
- `desktop/AIWorkstation.Desktop/App.xaml`
- `desktop/AIWorkstation.Desktop/MainWindow.xaml`
- `desktop/AIWorkstation.Desktop/MainWindow.xaml.cs`
- `desktop/AIWorkstation.Core.SmokeTests/Program.cs`
- `README.md`, `docs/REQUEST_TRACE.md`, and this log

## Verification

- Local XAML/XML parser: valid; 24 button click bindings resolved to code-behind methods.
- Native .NET build/test: to be verified by the Windows GitHub Actions runner; not claimed as locally compiled on Linux.
- Existing V0.5 local task data remains readable through backward-compatible nullable metadata fields.

## Limitations / risk

- Model-provider request traces are not observable through an externally launched interactive CLI. Imported JSON/JSONL can be forged and is not an authenticated billing record.
- Context size uses a character heuristic; savings are approximate characters, not exact Token or monetary savings.
- No unattended control of a remote VM is attempted; deployment to the user's Hyper-V guest still requires their Windows-side validation.

## Next steps

1. Verify Windows WPF compilation, native smoke tests and publish artifact in GitHub Actions; fix any failures with new timestamped routine logs.
2. Validate the interactive canvas and external CLI launch in a disposable Hyper-V Windows 11 VM.
3. Add optional officially supported streaming adapters that expose real tool/turn events, without third-party subscription token proxying.
4. Add per-task configurable context budgets, explicit operator approval and tested execution stop controls where supported.
