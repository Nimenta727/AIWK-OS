# AIWS V1.0 — Modular source recomposition

## The product boundary

The previous V0.9 strategy launched / embedded entire T3 Code and OpenClaw applications. That was not a source-level integration. **V1.0 replaces the default desktop entry point with an AIWS-owned offline UI**, its own .NET state machine, approvals, trace and secure native bridge. Original T3/OpenClaw server processes are not required for this frontend.

| Area | Module | Source origin | Scope |
|---|---|---|---|
| UI | `desktop/AIWorkstation.Frontend` | New AIWS React/Vite frontend | Projects, workflow nodes, step inspector, local trace |
| Visual primitives | `T3StatusDot` and `T3Skeleton` | Adapted from MIT T3 Code | Presentation only; original upstream revision pinned in NOTICE |
| Application service | `WorkstationController` | New AIWS .NET code | Creates, approves, starts, completes and persists tasks |
| Native shell | `ModularWorkstationWindow` | New AIWS WPF + WebView2 code | Offline UI assets, origin-restricted message bridge |
| Existing execution | `WorkflowEngine`, `StageLaunchCoordinator`, `AgentTools` | AIWS V0.7 | User-approved official CLI launch; no model credentials stored |
| Provider metrics | `RequestTrace` | AIWS V0.6 | Imported structured evidence; unknown usage remains unknown |

### Upstream review and licensing

- **T3 Code**, MIT, reviewed revision `8e8ff9b243e5a4c3a837c9033a134b62aac7dade`: extracted limited `ConnectionStatusDot` / `Skeleton` UI primitives and adapted them to remove the proprietary application state, internal RPC and Tailwind dependencies. Full notice at `third_party/t3code/NOTICE.md`.
- **OpenClaw Windows Hub**, MIT: inspected WinUI tray / capabilities / sandbox boundaries. No WinUI source copied into WPF; later migration requires an isolated Windows capability worker.
- **Kandev**, AGPL-3.0: architecture reference only. Do not copy AGPL sources directly into AIWS's MIT distribution without handling AGPL obligations.
- **Claude Code and Codex CLI**: separately installed official binaries. Their subscriptions are not transformed into unrestricted third-party API access.

### Security and runtime

The EXE ships static React assets in adjacent `ui-dist/`, mapped to `https://aiws.local/` using WebView2 virtual host mapping. Remote navigation and arbitrary host functions are disallowed. UI messages use allowlisted verbs (`state`, `workspaces.pick`, `tasks.create`, `steps.approve`, `steps.launch`, `steps.complete`, `steps.retry`). CLI launches require native confirmation, use official tools and the existing `WorkspaceGuard`; workspace validation is *not* a Windows sandbox. Opening or clicking the UI does not call any model. Model-token metrics exist only when structured evidence was provided.

### Build and delivery

On Windows 11 Hyper-V with .NET 10 SDK, Node.js 22 and WebView2 Runtime: `scripts/Build-NativeDesktop.ps1`. It compiles the UI, runs tests, then publishes an executable under `dist/native-desktop/` with the required `ui-dist` directory. CI does the same on `windows-latest`. A standalone `.exe` without its `ui-dist` is **not** a complete distribution yet.

### Next phases

1. Version the native bridge protocol and add per-request timeouts and cancellation.
2. Build a separate Windows execution worker with explicit permissions, durable queue and IPC.
3. Examine upstream T3 diff/terminal modules for dependency-safe extraction and carry original attribution.
4. Add Windows / Hyper-V GUI acceptance tests and a signing/distribution pipeline.
5. Improve model telemetry without extracting, reselling or proxying the subscriptions' private credentials.
