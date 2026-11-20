# Professional upstream frontends — V0.8 integration

Review and design date: 2026-11-20. Primary source: [T3 Code](https://github.com/pingdotgg/t3code), MIT; optional [OpenClaw](https://github.com/openclaw/openclaw), MIT. Source structures checked against current upstream repositories.

## Why the old UI was replaced

AIWS V0.7 uses a hand-drawn WPF sidebar and WPF workflow cards. That is not the polished professional editor requested. The V0.8 application opens in `ProfessionalShellWindow`, an intentionally thin Windows-native frame that displays **the actual HTML frontend served by the officially running upstream platform** in WebView2. The upstream DOM, interactions, layout and color scheme are controlled by its original frontend. The user does **not** see an AIWS imitation of T3 Code/OpenClaw.

## Precise migration scope

| Capability | V0.8 behavior |
|---|---|
| Main interface | Original T3 Code UI via its local server in WebView2, optional OpenClaw UI tab |
| Professional UI source | **Not vendored**; comes from a separately installed, user-run official frontend/server |
| Windows packaging | AIWS single-file .NET/WPF EXE with WebView2 dependency/runtime; upstream apps installed separately |
| Existing workflow | V0.7 native window opened via `AIWS 任务与流程`, unchanged |
| Claude/Codex | Auth remains with official upstream agents; neither OAuth token nor API key is imported into AIWS |
| Task state | Each platform's own task database; **no automatic state unification yet** |
| AIWS call tracing | Maintained in AIWS, does not claim to observe T3/Claw internal model requests |

## Architecture

```text
WindowsAIWorkstation.exe (WPF + WebView2)
  ├─ ProfessionalShellWindow [first-run home]
  │   ├─ T3 Code UI      → http://127.0.0.1:<user-confirmed port> → official T3 server
  │   └─ OpenClaw UI     → http://127.0.0.1:<user-confirmed port> → official OpenClaw gateway
  └─ Native AIWS task editor  → Existing .NET AIWorkstation.Core / local task store
```

A loopback URL restriction protects against accidentally loading public websites in the privileged embedded shell. The embedded frontend is **not given** an AIWS execution bridge, system scripting API, filesystem access, or provider credentials. External navigation is blocked, and no user-entered URL with a query/token/userinfo is saved. The original frontend may still connect to endpoints requested by the upstream app itself; its security model remains distinct. WebView2 browser data is stored under the current user's `%LOCALAPPDATA%/WindowsAIWorkstation`.

## UI choices and licensing

- [T3 Code](https://github.com/pingdotgg/t3code): preferred for original conversation/project/sidebar UI and direct support for separately signed-in official Claude Code/Codex; source is an interconnected React/Vite monorepo with client-runtime/RPC/server packages, so copying individual JSX files without that runtime would break behavior. MIT license supports a future *source-level* fork if we preserve notices and meet dependency requirements.
- [OpenClaw](https://github.com/openclaw/openclaw): optional original agent/dashboard UI; not an arbitrary source of model credentials. Its local Gateway has its own policy model.
- [Kandev](https://github.com/kdlbs/kandev): AGPL-3.0. Not copied into this MIT repository. A future source-level combination must undergo license review first.

## Validation and remaining tasks

1. `dotnet build` and core smoke tests on Windows CI (V0.8 must be verified separately).
2. In a Hyper-V Windows 11 guest, install WebView2 Runtime, launch T3 Code local server, connect to the printed local URL, test conversation/project pane, and test official CLI authentication.
3. Open AIWS native panel concurrently, edit a workflow and verify the local task store remains exclusive and intact.
4. Evaluate a **source-level fork** of T3 Code in a separate branch, with React/Vite client-runtime dependencies and a supported adapter API for AIWS workflow data. Only call that a migration once the original UI source has actually been copied and built, not merely hosted.
5. Add scoped integration and request trace adapters only using documented upstream interfaces. Never silently scrape credentials or bypass subscriptions.

The next milestone is **one shared navigation and data protocol**; V0.8 is the real upstream UI embedding foundation, not complete product unification.
