# 2026-11-20 11:45 +0800 — V1.1 developer tools and Windows capability modules

## Summary

Add a first functional implementation of the developer tool center. Unlike the previous external-platform launcher, it is implemented using AIWS-owned .NET services and modular React panels. One small MIT-licensed T3 Code table component is adapted and attributed; no T3 server and no OpenClaw/Kandev runtime is bundled.

## File changes

- `desktop/AIWorkstation.Core/GitWorkspaceService.cs`: fixed read-only Git command map, absolute executable lookup, non-shell execution, timeout, stdout cap, concurrent stream draining.
- `desktop/AIWorkstation.Core/WindowsToolPolicy.cs`: Windows capability inventory and explicitly user-initiated standalone PowerShell terminal.
- `desktop/AIWorkstation.Core/AgentTools.cs`: discover Git executable from fully qualified PATH entries without executing it.
- `desktop/AIWorkstation.Desktop/ModularWorkstationWindow.xaml.cs`: allowlisted native requests for Git inspection, capabilities and confirmed PowerShell launch.
- `desktop/AIWorkstation.Frontend/src/components/{DevToolsPanel,T3ReviewTable}.tsx`: local Git UI, review output and capability display; T3 Code component adapted under MIT.
- `desktop/AIWorkstation.Frontend/src/model/toolCommands.mjs`: frontend view identifiers and bounded output presentation.
- `desktop/AIWorkstation.Frontend/src/App.tsx`, `src/styles.css`: developer tools navigation and warm-light styling.
- `desktop/AIWorkstation.Core.SmokeTests/Program.cs`, `desktop/AIWorkstation.Frontend/tests/tools.test.mjs`: new regressions for read-only execution and command filtering.
- `third_party/t3code/NOTICE.md`: updated exact upstream source attribution.
- `docs/DEVELOPER_MODULES_V11.md`, `README.md`: integration boundaries, security caveats and user guide.

## Validation

- Local Python unittest suite: 38 tests passed.
- Local Node UI/model tests: 7 tests passed.
- Windows WPF/.NET build: requires GitHub Actions validation, not assumed from local tests.
- Hyper-V GUI validation: not yet performed.

## Next steps

1. Verify Windows CI build, core smoke tests and self-contained EXE artifact; fix compiler defects before release.
2. Exercise Git/Diff display and PowerShell confirmation in an actual Hyper-V Windows VM.
3. Implement an **actual in-app terminal** based on a constrained ConPTY worker rather than mislabeling a launcher as a terminal.
4. Add file/hunk review, clear per-tool permission contracts, and explicit request-level audit trails.
