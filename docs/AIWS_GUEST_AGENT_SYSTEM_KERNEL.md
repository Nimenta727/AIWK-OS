# AIWS OS unified guest AI/Agent, services and kernel candidate pipeline

**Delivery status:** experimental integrated control plane. The code has been committed; independent validation is ongoing. This document deliberately distinguishes what runs today from what is only staged.

## 2026-11-21 integrated architecture and outstanding acceptance gates

Production guest architecture is now AIWS React Shell → loopback UI adapter → same-UID AF_UNIX socket → independent unprivileged systemd user Agent → one persistent SQLite DAG/approval/audit store → allowlisted guest execution.

- Directory and file reads, code inspection, and workbench read-only jobs route through this Agent, without any model token requirement.
- Direct temporary file writes are rejected. Manual edits must create a durable file.replace DAG stage, receive explicit approval, and satisfy an expected SHA-256 precondition.
- Guest services are managed through allowlisted user-systemd operations only. Model suggestions are read-only, independently checked, saved pending, and never auto-executed.
- The independent guest-root-only EFI kernel A/B CLI is not callable through the AI Agent, HTTP, or Unix IPC. It requires an actual mounted FAT ESP, known-good A entry, trusted B kernel/initrd hashes, and manual administrator consent. A trial boot preserves A as the default. This is experimental, not a production watchdog solution.
- A separate GitHub CI job constructs a disposable GPT/FAT disk and attempts real OVMF firmware B-failure/A-recovery. Only a successful run with actual serial evidence qualifies as recovery acceptance.
- Optional model-inclusive Debian ISO requires a local license-reviewed and SHA-pinned Qwen3.5-2B GGUF and llama-server binary. The guest can verify root-owned immutable bundled GGUF and load it without copying multi-GiB weights to the volatile Live overlay; the service is off until expressly enabled.
- Two model gates are separate: actual networkless container CPU inference and actual QEMU guest inference from the model-inclusive ISO. Neither is claimed passed until their workflows complete successfully.
- NixOS ISO remains evaluation-only, not build-and-boot verified. A model or third-party parser cannot be assumed safe simply because it runs offline.

All AIWS APIs remain guest-only and deny host files, host shell, root, hypervisor control, shared folders or device passthrough. This is defense in depth rather than a guarantee against VM escape or malicious guest root.

## 1. Architecture

Guest AIWS React desktop → localhost 127.0.0.1:17640 HTTP (Host/Origin/CSRF) → one persistent GuestTaskStore SQLite DAG + audit chain → an allowlisted guest-only tool runner.

The React interface now has files, persistent plans, local-model suggestions and system/guest-kernel pages. Normal file clicks use local deterministic code, not cloud model requests.

The optional local model (llama.cpp on guest 127.0.0.1:18080) is **not a privilege broker**. It proposes one read-only structured tool. That proposal can be converted to an audited pending task. The user must explicitly dispatch. A generated tool proposal is validated again by a schema and guest capability allowlist.

GuestOperations provides:
- service.inspect: read guest-user aiws-workbench.service and aiws-local-model.service via a fixed systemctl --user show invocation.
- service.restart: only aiws-local-model.service, via an explicitly approved persistent DAG stage. No root, ssh.service, host service, arbitrary command, privileged broker or QMP.
- kernel.inspect: report the running *guest* kernel version without mutation.
- kernel.stage: from a guest workspace relative .fragment file, SHA-256 precondition, maximum 16 KiB, strict CONFIG_ allowlist, private stage snapshot and immutable source hash.
- kernel.verify: rehash candidate data and refuse mismatch.
- kernel.recovery_plan: record the known guest running kernel version and missing recovery prerequisites. Does NOT deploy a kernel.
- kernel.abandon: after explicit approval, mark a staged candidate abandoned, retaining the snapshot for audit. Does NOT roll back a running kernel.

## 2. Durable task recovery

GuestTaskStore persists goals, plan stages, dependency DAG, explicit approvals, tool results, error states and append-only-in-app hash-linked audit in a 0700/0600 private guest state directory.

The normal Linux guest controller uses an OS advisory singleton lock. At restart, queued/running stages are marked interrupted; write operations lose prior approval and need fresh confirmation. Failed and completed stages are not silently rerun. The local hash chain is verified before new mutations; missing/deleted/reordered log entries can block scheduling. Tool arguments are SHA-represented in task-created audit events rather than duplicated as plaintext.

Limits: it is a single-guest-user, serial task executor, not a multi-agent scheduler. SQLite audit cannot defend against guest root; preexisting arbitrary file contents in task arguments/results still need encryption/data lifecycle controls. A privileged guest service broker does not yet exist.

## 3. Offline 1–3B model

The first evaluation candidate is official Qwen/Qwen3.5-2B (post-trained model; source license Apache-2.0). The packaged offline inference adapter uses a guest-only llama.cpp backend and never falls back to cloud automatically.

A guest-only model registry allows the guest operator to import an already available regular GGUF model file from a dedicated guest project directory, with an explicit expected SHA-256 and acknowledgement to review its license. It pins the version in private guest storage, verifies the active model before enabling or starting inference and can restore earlier versions while the inference service is off. Neither the official model weights nor any third-party quantized GGUF are bundled with this release. Actual llama.cpp compatibility and exact source/quantization provenance must be validated before shipping weights. Startup service is disabled by default, CPU-only and limited by guest user memory/CPU controls. It never gets host GPU passthrough.

Example guest-only CLI contract (after an authorized GGUF exists inside the guest):
- guest-only python runtime: /usr/local/lib/aiws/aiws_model_registry.py
- verification mode: --verify
- manual version import: --import-guest RELATIVE_FILE.gguf --sha256 TRUSTED_64_HEX --accept-source-license
- prior version switch: --rollback TRUSTED_64_HEX (model service must be off)

These are tool interfaces, not a guarantee of a verified quantized model. Loading arbitrary GGUF remains a parser attack surface, so guest isolation and source review are mandatory. LoRA training is still an opt-in, guest-only recipe; no adapter is trained or validated yet.

## 4. Kernel recovery — two distinct meanings

**Implemented:** recovery/abandonment of the guest-only *staging candidate*. A staged fragment, source hash, running kernel release, metadata and controlled abandonment can survive a guest service restart and can be audited.

**Not implemented:** actual recoverable Linux kernel upgrade/rollback. That needs independently validated *guest-only* kernel compilation, package signatures/hashes, an inactive kernel slot, preserved known-good kernel+initramfs, an offline snapshot, bootloader selection and boot health watchdog, forced reboot testing, and automated rollback without any host control API. The system reports bootRecoveryReady=false and refuses to pretend the candidate has been deployed.

## 5. Four release gates

1. GUI: Debian guest-only AIWS Shell/Chromium kiosk, file and DAG interactions are already QEMU verified; extended kernel candidate approval click test must separately pass. Firmware-boot and long-term user experience remain untested.
2. Agent parity: unify persistent Linux DAG and approved tools; advanced orchestration, idempotency under real crash and multi-agent scheduling remain to do.
3. NixOS: declarative expression evaluated, ISO not yet built/booted.
4. Isolation/recovery: guest marker, VM detection, forbidden mounts, unprivileged user, capability allowlists, current staging integrity; real permission broker, signed kernel A/B, formal security test remain.

## 6. Next engineering plan

- Run and inspect the current real Debian ISO/QEMU GUI kernel-candidate acceptance, and add continuous stability/restart test evidence.
- Acquire a license-cleared, hash-pinned quantized 2B model **inside a dedicated disposable guest**, confirm llama.cpp actual inference, then evaluate latency, accuracy, parameter validity, resource consumption and rollback. Fine-tune only if a controlled baseline indicates benefit.
- Establish a separate guest-only privilege/permission broker with explicit capability grants and rollback; do not add a generic root shell.
- Build/boot a real locked NixOS image and prove its AIWS GUI parity with Debian.
- Develop a versioned A/B kernel slot implementation in a disposable dedicated guest and exercise both success and forced-failure restoration before enabling real kernel deployment.

## 7. Known security boundary

No host filesystem, host shell, host kernel, host network bridge, hypervisor API, shared folders or device passthrough are exposed by AIWS application APIs. This is defense in depth, not a proof against hypervisor vulnerabilities, a malicious guest root process or a compromised third-party model parser. Only run experimental builds in an isolated disposable VM.
