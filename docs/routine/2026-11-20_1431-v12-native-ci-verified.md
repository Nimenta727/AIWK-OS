# 2026-11-20 14:31 (+08:00) — V1.2 Windows native CI and artifact verified

## Verified results

- GitHub Actions native workflow on commit `2e5e2c7d165a04a5a892c9bf2a0e2cfba3de9655`: **success** — https://github.com/Nimenta727/Windows-AI-Workstation/actions/runs/44688011400
- React/TypeScript frontend: `npm test` and production `vite build` passed, including 10 frontend model tests.
- WPF/.NET 10 Release compilation and .NET core smoke tests passed on Windows: real Git repo, file diff and preview, commit path report, traversal and symlink restrictions, persistence and approval checks.
- Self-contained Windows x64 EXE artifact uploaded: `WindowsAIWorkstation-Native-win-x64`. Downloaded ZIP was inspected: `WindowsAIWorkstation.exe` (~62.3 MiB), `ui-dist/index.html` and compiled offline CSS/JS.
- Existing Python checks passed in CI and all 38 legacy Python tests passed locally.
- Two test-harness CI issues and their fixes are documented in `2026-11-20_1426-*` (variable scope) and `2026-11-20_1433-*` (Git for Windows read-only file cleanup).

## Unverified / limitations

- GitHub CI does **not** prove actual Hyper-V Windows GUI functionality, WebView2 startup, native CLI account login, Windows DPI behavior or permissions.
- Stage-associated file changes are **observations**, not causal evidence that Claude/Codex authored edits. File bodies are not automatically added to model prompts.
- Distribute the entire ZIP; `WindowsAIWorkstation.exe` needs sibling `ui-dist/` files.

## Next

1. Test the EXE in the target Hyper-V guest with real repos, staged/unstaged/untracked edits, renames and commits.
2. Validate large workspaces, symlinks, binary files and permission failures as a non-admin Windows user.
3. Implement Agent-isolated worktrees and instrumented tool events for stronger provenance.
4. Add approval-gated per-hunk Git review and optional source-code navigation without automatic Token use.
