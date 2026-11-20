# 2026-11-20 09:50 +0800 — V0.6 native request-flow build verified

## What changed

- Recorded the completed Windows CI verification for native V0.6 flow visualization after the WPF inspector correction.
- Confirmed the generated Windows x64 executable is bundled by the Windows GitHub Actions workflow.

## Code and documentation status

- Primary flow implementation: commit `e78565fe625274d7bd57e587b1b3d4df13d0f791`.
- WPF layout and duplicate-start correction: commit `b60c3334bb9fb492f47c80077719520768bb18c6`.
- This routine file documents successful CI outcomes and future checks without modifying product code.

## Verification

- GitHub Actions run: https://github.com/Nimenta727/Windows-AI-Workstation/actions/runs/44655442859
- Windows WPF Release compilation: passed.
- Native core smoke tests: passed, including token metadata and call-flow evidence checks.
- Self-contained Windows x64 EXE publish: passed.
- GitHub Actions artifact upload: passed (`WindowsAIWorkstation-Native-win-x64`, artifact ID `14592438861`).
- Legacy Python regression tests: 38/38 passed in local execution.
- Not yet verified: launch, layout and CLI integrations inside the user's specific Hyper-V guest.

## Known limitations

- Interactive Claude Code / Codex internal API calls are not intercepted.
- Real usage is only reported from manually imported structured records whose authenticity the application does not verify.
- Pre-call size warning is advisory, not a hard Token budget enforcement.

## Next steps

1. Run EXE on a disposable Hyper-V Windows guest; verify layout, scrolling, clicking, trace export and provider log import.
2. Test account-authorized external CLI processes without copying or exporting provider credentials.
3. Add optional officially supported structured stream adapters and real stop/cancellation support, when permitted.
4. Consider versioned signed Windows installer and upgrade strategy after functional acceptance.
