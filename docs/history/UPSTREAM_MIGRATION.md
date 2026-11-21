> **双语导读 / Bilingual overview (2026-11-20)**
>
> 中文：成熟平台参考和源码许可证迁移。保留历史正文及原始测试/风险描述，不能据此宣称现版已通过新的 Hyper-V 运行验收。
>
> English: Upstream references and source-level license requirements. The historical narrative and original test/risk statements remain intact; this is not evidence of fresh Hyper-V acceptance.
>
> [总索引 / Docs index](README.md) · [当前发行 / Release](RELEASE_NOTES_V19.md)

---

# Upstream migration decisions — AIWS V0.3

Review date: **2026-11-19**. The goal is a maintainable Windows-native control plane, not a monolithic copy of several upstream programs.

| Upstream project | Source/license reviewed | Feature pattern now implemented | Code copied? |
|---|---|---|---|
| [T3 Code](https://github.com/pingdotgg/t3code) | [architecture](https://github.com/pingdotgg/t3code/blob/main/docs/internals/overview.md), [MIT](https://github.com/pingdotgg/t3code/blob/main/LICENSE) | Explicit provider selection and user-approved, per-task Git worktree isolation | **No**; independent stdlib Python + Git implementation |
| [Kandev](https://github.com/kdlbs/kandev) | [architecture](https://github.com/kdlbs/kandev/blob/main/docs/ARCHITECTURE.md), [AGPL-3.0](https://github.com/kdlbs/kandev/blob/main/LICENSE) | SQLite-backed stages, workflow state transitions and human handoff | **No**; uses workflow concepts only, not AGPL source |
| [OpenClaw Windows Hub](https://github.com/openclaw/openclaw-windows-node) | [node capabilities and approvals](https://github.com/openclaw/openclaw-windows-node/blob/main/README.md), [MIT](https://github.com/openclaw/openclaw-windows-node/blob/main/LICENSE) | Explicit opt-in gates and locally controlled Windows execution | **No**; existing security boundary remains, no UI driver yet |

## Why we did not vendor whole repositories

- T3 Code is a large Electron/TypeScript stack; copying orchestration internals into this Python application would sever upstream contracts and complicate security updates.
- Kandev uses **AGPL-3.0**. It is not included in this project's differently licensed source. Copying implementation code would require a compatible licensing/distribution plan and notice obligations.
- OpenClaw's Windows Hub is a separately maintained Windows companion with its own gateway and device trust model. AIWS must not pretend to inherit those sandbox controls.
- Claude Code and Codex are **installed from official sources**, not bundled or token-proxied. A shared subscription does not imply an unrestricted third-party inference API.

## V0.2 acceptance

1. Existing V0.1 data opens and remains readable; legacy completed work stays complete.
2. Dual tasks have exactly three stages (Claude analysis, Codex implementation, Claude review).
3. Each stage needs a saved brief and explicit human result before advancing; the prior result is clearly treated as untrusted context.
4. Worktree creation requires a Git-initialized clean trusted project, explicit operator confirmation, deterministic branch/workspace, and no automatic merge or push.
5. No upstream source files or proprietary CLI binaries are included in portable ZIP.

## Next migration candidates

1. **T3**: Review supported public provider/ACP integration surfaces; implement tested adapters rather than importing private RPC internals.
2. **Kandev-inspired**: Durable job receipt/outbox and cancellation with recoverable states (independent implementation).
3. **OpenClaw-inspired**: Windows capability broker, per-tool allowlists, user approval audit and sandbox evidence.
4. **Windows**: Verify Hyper-V guest Worktree, PowerShell Direct, NTFS access control and actual CLI authentication paths.

## V0.3 independently implemented improvements

- T3-inspired provider separation: `CLIAdapters` advertises support, and the Codex worker is explicitly read-only; Claude remains interactive.
- Kandev-inspired durable intent: persisted `approvals` and `jobs` rows, one-time consumption, restart reconciliation and queue state views. **No AGPL code copied.**
- OpenClaw-inspired capability boundary: local policy descriptor with deny-by-default tool categories and per-request approvals, without borrowing or falsely claiming Windows Hub sandboxing. **No upstream code copied.**
- Further Windows/Hyper-V integration remains blocked on testing the actual guest; no native third-party binaries included.
