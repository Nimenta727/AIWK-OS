> **双语导读 / Bilingual overview (2026-11-20)**
>
> 中文：Studio 视觉层次、操作反馈与浏览器点击测试。保留历史正文及原始测试/风险描述，不能据此宣称现版已通过新的 Hyper-V 运行验收。
>
> English: Studio visual hierarchy, interaction feedback and browser click tests. The historical narrative and original test/risk statements remain intact; this is not evidence of fresh Hyper-V acceptance.
>
> [总索引 / Docs index](README.md) · [当前发行 / Release](RELEASE_NOTES_V19.md)

---

# AIWS V1.8.1 — Studio-quality frontend & interaction reliability

> 2026-11-20 · UI implementation and test plan. Builds on the V1.8 agent orchestrator; not a replacement runtime.

## Objectives / 设计目标

将 Windows AI Workstation 从功能拼接的界面整理为成熟的桌面工作台，同时让每个可点击控件都具有明确动作和结果反馈。

- **Visual**: professional obsidian project navigation, porcelain work surface, terracotta highlights, consistent spacing/shadows, clear typography, focused content density, restrained transitions.
- **Workflow**: place Mission Control, Markdown Plan Studio, Git project tree and Execution Atlas in a full-width working area; only mount the stage inspector on the workflow page.
- **Interaction**: keyboard and mouse parity, task search, Ctrl+K / Ctrl+N, focus trapping, Escape-close for dialogs, Enter-to-create, real disabled/loading states, errors and success announcements, deterministic navigation, no inert profile/settings button.
- **Correctness**: never double-submit native mutations, never let an older state read overwrite a newer snapshot, ensure local folder picker cannot race with another mutation, distinguish read and write transport timeouts. Write operation timeout means the result is **unknown**, not failed or safe to retry.
- **Terminal**: buffer fast keystrokes and relay them sequentially to native ConPTY, rather than sending a request for each character and overflowing bridge pending capacity. Explicitly report uncertain delivery; do not silently retry input/commands.
- **Plans**: bind plan versions via the same top-level guarded mutation path as other AIWS operations.

The visual redesign **does not** add API calls, telemetry, token usage, remote content, web fonts or external UI services. Windows/WPF remains the app host; React assets remain offline under `ui-dist`.

## UI structure / 交互规格

1. Sidebar: grouped primary workspace, evidence and developer tools; keyboard-searchable recent tasks; no non-functional controls.
2. Mission: prominent task heading, stage statistics, queue and confirmed next action, existing agent evidence view.
3. Main content: canvas scrolls independently; inspector is present only for an actual workflow task. At narrower widths, inspector becomes an explicit slide-over pane with close controls.
4. Create dialog: native folder picker with busy guard, accessible field labels, keyboard trap, Enter submit, Escape dismiss, explicit workflow template selection and one canonical submit button.
5. Feedback: connection failures offer an actual retry control; mutations expose a pending state; success only after native acknowledgment; transport uncertainty never masquerades as success.
6. Terminal: output remains session-only and does not become model context. Input batching preserves sequence and avoids per-character UI messages.

## Interaction invariants / 高优先级边界

- A duplicate click on `tasks.create` or `steps.launch` cannot dispatch two native RPCs from the same app window while one is pending.
- Out-of-order `state` replies do not replace a newer state (versioned read guard); reads during an in-flight write are ignored until confirmation.
- Read-only RPC timeout: refresh can be attempted; write timeout: outcome unknown; **never** auto-retry a side-effecting request.
- A modal cannot be submitted without an explicit task name and folder; while native folder picker is open it cannot be closed by backdrop or Escape.
- Error handling remains visible inside the open create modal rather than hidden beneath its backdrop.
- A task plan binding uses the same guarded application mutation handler; no direct unguarded bridge call.
- The presence or appearance of controls cannot falsely claim actual provider model requests, Token usage or an OS sandbox.

## Tests / 验收

- Node unit tests: search/order, shortcut modifiers, read/write timeout semantics plus existing workflow/plan/project/mission tests.
- Playwright browser checks (compiled frontend, local host **mock**, no live CLI): navigation, task selection/search, keyboard shortcut, create modal, template selection, single submission under delayed native reply, narrow viewport inspector, primary panels.
- Windows CI: Node tests, TypeScript/Vite build, Edge-based UI browser tests, WPF/.NET build, core smoke and self-contained EXE packaging.
- Manual pending: Windows Hyper-V guest with real WebView2, DPI scaling 100–200%, IME/keyboard navigation, native directory picker, ConPTY high-rate typing, real task/plan/Git interactions. Browser mocks are not a substitute for this test.

## Known limitations / 局限

- Native WPF dialogs and actual CLI processes cannot be fully tested with a fake browser bridge; Hyper-V GUI acceptance remains mandatory.
- The existing V1.8 architecture is human-supervised. UI optimization does not make Claude/Codex fully unattended.
- The terminal buffer prevents bridge overload from typical typing but does not provide an OS sandbox or transactionality for shell commands.
- Single EXE is not a complete distribution without adjacent `ui-dist` resources.

## Next steps / 后续

1. Verify the new rendered UI and workflows in the user's Hyper-V Windows VM, including DPI, WebView2 focus, file dialogs and ConPTY.
2. Audit all remaining project/atlas/plan component actions for accessibility, race conditions, cancellation and stale data.
3. Add durable browser-driven integration tests for *actual native host* via VM test automation and independent app permissions.
4. Improve project diff and DAG canvas ergonomics without increasing model calls or duplicating orchestration state.
