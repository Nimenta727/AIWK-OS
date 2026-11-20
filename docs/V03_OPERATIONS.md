> **双语导读 / Bilingual overview (2026-11-20)**
>
> 中文：早期 Python 原型部署与旧版操作说明。保留历史正文及原始测试/风险描述，不能据此宣称现版已通过新的 Hyper-V 运行验收。
>
> English: Legacy Python prototype setup and archived operations. The historical narrative and original test/risk statements remain intact; this is not evidence of fresh Hyper-V acceptance.
>
> [总索引 / Docs index](README.md) · [当前发行 / Release](RELEASE_NOTES_V19.md)

---

# AIWS V0.3 — Operator runbook (Hyper-V Windows guest)

## Upgrade from V0.2

1. Back up `%USERPROFILE%\AI-Workstation\aiws.sqlite3` with AIWS **stopped** and make an independent VM backup. Do not treat a checkpoint as a backup.
2. Extract the new V0.3 portable archive into a **new code folder**; do not overwrite any running install. Data remains at `%USERPROFILE%\AI-Workstation`.
3. Open PowerShell as a **non-administrator** in the extracted directory and run `python -m unittest discover -s tests -v`.
4. Execute `./scripts/Start-AIWS.ps1` for manual operation or, only after evaluating the risks, `./scripts/Start-AIWS.ps1 -EnableCodexReadonly` for opt-in background read-only jobs.
5. Log in to official `claude` and `codex login` in the same Windows account if sessions have expired. Do not export session cookies, OAuth tokens or local CLI authentication files.
6. Open `http://127.0.0.1:8765` **inside the guest**. Check `/api/health` and dashboard tool inventory.

The SQLite migration is additive (`approvals`, `jobs`), preserving existing projects, tasks and workflow steps. A running task detected on startup is marked failed; the operator must inspect its external effects before retrying. A second AIWS instance for the same workspace is rejected. Do not use a shared SMB/OneDrive folder for the live database.

## Approval and recovery drills

- Create a new `codex` task in a trusted Git project, then prepare it.
- Request read-only execution; verify the CLI does **not** start while approval is pending.
- Deny the request once; verify it does not enqueue any job.
- Request again, approve once; verify that a job appears under Jobs and executes only when the opt-in worker is enabled.
- Try approving the same request again; it must fail.
- For a cancelled queued job, you may request a fresh approval. Running tasks are not cancellable through this V0.3 interface.
- Simulate an interrupted run only in a disposable test project and after saving any changes: restart the application while a job is running, and ensure the job appears as `interrupted`, not silently rerun.

## Security checks

- Confirm the service binds only `127.0.0.1`, not the Hyper-V external vSwitch or all interfaces.
- Do not enable unrestricted OS rights or mount host folders into the guest for an Agent.
- The policy matrix is descriptive and is **not** a Windows sandbox. MCP extensions may perform actions outside Codex's read-only file sandbox.
- Disable untrusted MCP servers, extensions and project-level hooks before approving background jobs. Use separate low-privilege Windows user accounts for sensitive data.
- Review stored job output before exporting files or logs. The database stores task descriptions and model output, not provider login tokens.
- Use official source installers for Claude Code and Codex CLI. The portable ZIP contains only AIWS's own source.

## Follow-up milestones

- Windows CI acceptance and Hyper-V guest UAT: native CLI invocation, PowerShell script tests, rollback and NTFS ACL checks.
- Robust child-process cancellation and bounded streaming logs.
- Signed Windows installer and cross-version executable discovery.
- Compatible official provider adapters when upstream terms and APIs support them, independent of any subscription credential proxy.
- User-approved Windows GUI automation module with explicit allowlists and an OS-level sandbox evaluation.
