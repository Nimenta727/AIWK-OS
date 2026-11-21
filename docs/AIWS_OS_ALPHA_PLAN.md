# AIWS OS Alpha 0.1 — engineering execution gates

**Status:** authorized roadmap, **not completed features**. Source of truth for staged M1–M4 acceptance. Existing Linux guest and Windows workstation remain separate.

| Milestone | Scope | Hard acceptance |
| --- | --- | --- |
| **M1 Install & recover** | UEFI install to disposable qcow2; persisted /home; A/B update and rollback | Boot without ISO, verify persisted data, inject update failure and restore previous boot slot |
| **M2 Shell 2.0** | launcher, terminal, browser, IDE, files, notifications, multiwindow, IME | Guest GUI click/keyboard/clipboard/Chinese IME tests; no developer console required |
| **M3 Mandatory security** | distinct Broker/Worker UIDs, Linux namespaces, cgroup budgets, seccomp and MAC profile | OS blocks unauthorized writes even when Agent is compromised; audit and approval integrity verified |
| **M4 Agent runtime** | plan → reviewed DAG → execute → verify → recover; model routing and multi-Agent | Real guest task benchmark with deterministic tool traces, failures and explicit approval |

## Dependency order

M1 disk installation must never run on a host disk. M2 UI can progress alongside M1, but GUI convenience cannot bypass M3. M4 model proposals must remain non-executable until DAG approval and isolated worker authorization. The legacy Windows task importer remains read-only.

## Immediate increment

- Implement a **read-only** VM/UEFI/disk preflight and explicit refusal of install requests.
- Extend Shell with native launchers, shortcut contracts and optional Chinese input support, without making UI code privileged.
- Build isolated disposable qcow2 integration tests **before** enabling any disk writes.
- Keep original BIOS/UEFI ISO boot acceptance and model benchmark distinct from installed-system acceptance.

## Release policy

No Alpha installation release until all M1 hard gates have completed CI with preserved logs/artifacts. No “secure autonomous OS” claim until M3 adversarial tests prove a kernel-enforced boundary. Keep failed, pending and not-run evidence explicit.
