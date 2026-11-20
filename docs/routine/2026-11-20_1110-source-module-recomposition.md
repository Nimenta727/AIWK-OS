# 2026-11-20 11:10 +0800 — Modular AIWS V1.0 source recomposition

## Changes

- Replaced embedded T3/OpenClaw app frontends as the default shell with an AIWS-owned offline React UI hosted by native WPF.
- Implemented local workflow canvas, token/trace panel, stage inspector, integration status, and task creation.
- Extracted two small MIT-licensed T3 Code UI components, adapted to independent AIWS UI; added pinned attribution.
- Added standalone `WorkstationController` applying existing task state, approvals, persistence, CLI launch and error handling without Web RPC.
- Introduced a WebView2 virtual host bound only to local shipped assets, with an action allowlist and native launch confirmation.
- Added frontend model tests and native controller smoke tests; updated Windows build/CI for frontend compilation.

## Validation

- Local `node --test`: five tests passed.
- Native Windows compilation/packaging requires GitHub Actions because the current editing environment has no .NET SDK.
- Hyper-V desktop acceptance still pending.

## Remaining work

- Only T3's small presentation primitives are source-ported so far; this is not a full upstream source migration.
- CLI execution runs as the current Windows user; no OS-level sandbox.
- Real per-request model usage remains unknown until official logs can be imported.

## Next steps

1. Verify Windows CI EXE, offline UI resources and C# smoke tests; fix all build failures.
2. Split the Windows worker out of UI process and add versioned bridge contracts.
3. Source-port isolated terminal/diff interactions from compatible MIT upstream modules.
4. Validate inside the user's Hyper-V guest before considering unattended use.
