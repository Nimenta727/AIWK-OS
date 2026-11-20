# 2026-11-20 11:33 +0800 — V1.1 Windows CI verification and release artifact

## What changed

- Verified that V1.1 Git/Diff review and Windows tool modules compile into the native, offline Windows desktop application.
- Recorded Windows CI evidence and clarified the distinction between native Git output, interactive PowerShell, and model invocations.
- No extra model API usage is required to open these modules or inspect Git data.

## CI evidence

- Source commit: `5b5980dd3f7235fb9391c3a391b8386cfa2b298d`
- Windows EXE CI: https://github.com/Nimenta727/Windows-AI-Workstation/actions/runs/44668118603 — **success**.
- Frontend npm tests: **7 passed**.
- WPF/.NET Release build and core smoke tests: **success**.
- Self-contained win-x64 EXE publication and Actions artifact upload: **success**.
- Python regression CI: https://github.com/Nimenta727/Windows-AI-Workstation/actions/runs/44668118607 — **success**.
- Local Python regression tests: **38 passed**.
- Actual Hyper-V Windows guest GUI/permission testing: **not yet performed**.

## Files affected

- `docs/routine/2026-11-20_1133-v11-windows-ci-verified.md` (this verification report)

## Known limitations

- The V1.1 `终端` tab opens an explicitly user-confirmed **separate** Windows PowerShell console. It is not yet a full embedded PTY.
- Read-only Git commands run with current Windows user's privileges; this is not an OS-enforced sandbox.
- The view does not read, copy, or store model credentials, and Git command output is ephemeral; the CLI's internal token usage is not inferred from process state.

## Next steps

1. Install the V1.1 CI artifact inside the user's Hyper-V VM, confirm real-world Git/Diff output, shell confirmation and DPI rendering.
2. Design a bounded Windows ConPTY worker and a native/React terminal with process lifecycle controls.
3. Add structured per-file/hunk Diff review with explicit approval actions and no implicit git stage/commit/push.
4. Build a least-privilege Windows executor isolated from the desktop UI process and document its permission boundaries.
