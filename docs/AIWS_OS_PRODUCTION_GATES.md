# AIWS OS from bootable demo to usable AI-native OS
# AIWS OS 工程级验收：固件、桌面 Shell、独立权限 Broker

> Engineering candidate, not a released or physically validated operating system.
> 2026-11-21: Debian primary; NixOS exploratory.

## F — original firmware ISO and recovery

The existing direct-QEMU-kernel path checks the live guest services and GUI,
but bypasses the ISO firmware/El Torito chain. The new matrix in
.github/workflows/aiws-os-image-boot.yml boots the actual generated ISO
through SeaBIOS and OVMF UEFI, without -kernel or -initrd. It checks the
El Torito BIOS/UEFI entries and requires the existing in-guest GUI/DAG
smoke receipt. Firmware serial logs and boot-record evidence are uploaded
separately. CI is authoritative only after BOTH jobs complete successfully.

The existing GPT/ESP systemd-boot A/B recovery fixture is a separate
kernel-slot disk test; it does not certify ISO boot, a persistent installer,
Secure Boot or hardware recovery.

Further gates: physical x86 UEFI/BIOS, USB boot, installation and storage
migration, secure boot policy, A/B atomic system updates, interrupted
updates and display/keyboard hardware compatibility.

## S — interactive native Shell

Current bridge Shell: Openbox windows, XFCE taskbar, normal maximized
Chromium app window instead of exclusive kiosk, Super+Enter terminal,
Super+E Thunar, Alt+Tab task switching. Real X11 focus and synthetic
UTF-8 clipboard roundtrip are tested separately from Selenium browser
clicks and the persistent task approval and execution flow.

Still open: AIWS-owned notification/approval tray, accessible multiwindow
navigation, reliable Chinese IME, copy/paste between distinct applications,
multi-monitor/DPI, session lock and recovery, desktop resource and queue
widgets, approved native IPC. Web content must never gain a general-purpose
native command or host bridge. Native OS integrations require narrow
typed endpoints, explicit user activity and audit trails.

## P — independent permission decision point, then mandatory enforcement

The existing same-UID Agent and SQLite DAG gate high-risk writes by
approval and tool allowlists. This is valuable application-level checking
but **not** a Linux mandatory access-control boundary.

Implemented application-level candidate: a separate fail-closed, non-root
same-UID Permission Broker that reads the persisted DAG and approves only
its exact running stage,
arguments and approval state; no forged Boolean from UI may authorize
writes. Bind decisions to capability, workspace, execution identity,
stage, risk budget and TTL. Test denial and loss of the Broker, malformed
IPC, replay, stale approval, parameter substitution and cumulative misuse.

A user-level Broker alone cannot prevent processes running with the same
UID from bypassing the Agent IPC. True mandatory enforcement requires
a separate low-rights worker UID and protected policy/SQLite storage,
workspace confinement (Landlock/openat2/mount namespaces), OS MAC policy
(e.g. AppArmor), network egress controls, revocation and adversarial VM
escape/bypass testing. Do not introduce a privileged root daemon merely
to make the Broker look authoritative. Hash-linked local records and
optional TPM attestation have different guarantees; neither equals
tamper-proof guest-root protection by default.

## A — bounded autonomy after enforcement

The Linux Agent already uses a persistent SQLite DAG and user systemd unit;
Windows plans, WorkItems, AgentRuns and evidence import as non-executable
history without inherited approval. Preserve those invariants.

Parallel model track: independent bilingual held-out prompts, explicit
refusal rate, valid tool/argument selection, QEMU guest P95 latency and
peak memory. A real benchmark pass is required before a measured claim.
Future autonomous planning requires caps on steps, wall time, context,
tool calls, risk and retries, with fail-closed per-tool authorization.

## Evidence and release gates

| Area | Implemented or CI instrumented | Not yet demonstrated |
| --- | --- | --- |
| Firmware | Two ISO firmware matrix jobs plus old direct-kernel diagnosis | Successful results for new CI, actual hardware and installer |
| Shell | XFCE panel, Openbox, normal app, X11 input/clipboard checks | Full Chinese IME, all desktop UX and real-world peripherals |
| Broker | Separate same-UID policy server, Agent/MCP fail-closed route and tests (CI pending) | Truly mandatory OS isolation under separate worker credentials |
| Model | Qwen3.5-2B guest benchmark harness | Accepted model results and robust autonomous loop |
| Migration | Windows evidence imported as non-executable history | Complete native live DAG mapping and review of tools |
| Release | Debian experimental CI recipe | Update/rollback/installer/license/SBOM/accessibility/hardware |

Always report implementation, CI evidence, and physical acceptance separately.

Current code and limitations: [Independent Permission Broker](AIWS_PERMISSION_BROKER.md).
