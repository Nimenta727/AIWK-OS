# AIWS OS priority register — mandatory acceptance gates / 强制执行的四项主线

**Policy: AIWS OS is guest-only. No operations on the host system.**

## P0-A: Workbench GUI actually visible and operable

Acceptance requires a real VM boot, visible AIWS workbench (not only XFCE process/localhost JSON), screenshot/frame evidence, verified clicks for navigation, file composition, task submission and completion/error display. Current run 44762589191 verified kernel, LightDM, XFCE session, agent HTTP and MCP; it **did not verify a displayed workbench**. The existing framebuffer showed a black desktop with mouse cursor. Keep a rescue terminal only for maintenance and do not rely on a traditional file manager.

Do not label this complete before a guest browser / GUI interaction test passes.

## P0-B: Windows task/plan/DAG/Agent/audit semantics moved to Linux

Target a shared schema and guest-local persistent engine, not a separate UI-only clone. Preserve durable task IDs, plans and revisions, DAG dependency validation, queued/running/failed/interrupted transitions, approval gates, artifact hashes, audit evidence and recovery. Existing Python OS guest agent is currently an MCP tool-queue, **not** the Windows equivalent.

Acceptance: cross-restart persistence, deterministically reproducible DAG ordering, explicit privilege approval, no unintended double-dispatch, evidence linkage and tests for failure/reboot recovery. UI and Agent use the SAME state service.

## P1-C: NixOS image construction and real boot

NixOS ISO expression parse/eval passed; **not built or booted**. Need immutable Nix input lock, fixed frontend build, NixOS image job, VM boot probe and captured GUI evidence. Debian remains the validated fallback boot adapter until NixOS equivalence is demonstrated. Disable autologin for any networked/non-disposable distribution.

## P1-D: Guest service/permissions/containment and recovery

AI may manage **guest workspace and guest OS kernel sources**, subject to reviewable patch/compile/test/recovery pipeline. VM kernel builds and versioned image deployment happen INSIDE a disposable guest or CI build worker that has no host access. AI never receives host root, host kernel access, host volumes, host shell, host filesystem API, QMP/libvirt/Hyper-V control, shared folders or guest-host agent bridge. Deny host-sharing filesystems, user-visible hidden mounts and VM passthrough. Future guest-side broker will require explicit capability/operation scopes, authenticated local boundary, audit, timeouts and rollback; no unrestricted root endpoint.

## Supporting features subordinated to the gates

- AI-managed file browser: user can view file composition, AI uses guest-only tools to organize files; manual actions remain optional. The UI is the primary shell, XFCE is legacy/maintenance layer.
- Offline 1–3B model: optional local planner/operator in guest. Do not reserve a guaranteed 3–5GB VRAM (architecture, model quantization, context KV cache and runtime change memory). Start with CPU mode. No GPU passthrough or host device access. The local model may **propose** bounded guest tools, but the enforcement layer is independent.
- AI kernel edits: prepare guest kernel patches, builds, tests and signed/hashed replacement images with rollback; never live rewrite host kernel, never allow agent to mutate the running kernel without the guarded workflow.

## Verification status as of this register

- Debian experimental smoke ISO built and hashed in real GitHub Actions.
- QEMU direct kernel + initrd boot returned AIWS_BOOT_SMOKE_PASS on run 44762589191, confirming guest kernel, desktop session, web API and MCP; not a full firmware ISO boot.
- NixOS declarative module parse/eval passed; NixOS ISO unbuilt.
- New guest-only marker, VM detector and mountpoint policy under OS static tests; the boundary is defense in depth and is not proof against hypervisor vulnerabilities or malicious guest root.

## Release blocking checklist

- [ ] P0-A visible workbench and automated UI interactions in real VM
- [ ] P0-B persistent task/plan/DAG/audit runtime and compatibility tests
- [ ] P1-C NixOS built ISO with real VM boot and GUI evidence
- [ ] P1-D guest permissions, isolated execution and recovery safety acceptance
- [ ] Host deny invariants tested independently, no host bridge in any image
- [ ] Model-free core usability and optional offline model; no network dependency by default

**Do not substitute extra features for these milestones.**

## Latest implementation after priority register (still gated)

- **P0 GUI:** Debian LightDM's experimental offline profile now chooses an AIWS-only Xsession (Openbox is only minimal window management; Chromium launches in kiosk mode). An in-guest ChromeDriver test must visibly click files, inspect content, create/execute a SQLite task and check the disabled model status before reporting PASS. Real QEMU result is a separate acceptance and must be checked.
- **P0 unified DAG:** os/runtime/aiws_tasks.py now persists guest tasks/stages/dependencies/approvals/audit chain in SQLite, and workbench HTTP/React UI exposes plan creation, explicit stage dispatch and evidence. Windows task model parity, interrupted adapter recovery and complete execution orchestration still need deeper validation.
- **P1 NixOS:** declared adapter compiles/evaluates; full ISO build and GUI boot remain incomplete. NixOS still uses an XFCE session and has not switched to the new AIWS Shell.
- **P1 guest permissions:** guest-only VM/marker/mount guards and read-only local model proposal validation implemented; full permission broker/resource limits/rollback not complete.
- **Local 2B model:** optional guest-only llama.cpp service script, intent proposal API, dataset validation and offline LoRA training recipe committed. Neither pretrained weights nor LoRA adapters are bundled or trained; CPU/VRAM and tool accuracy in a real guest remain unmeasured. No host GPU passthrough.

**Release status remains experimental. Do not mark P0 GUI passed before actual guest UI click evidence.**


## 2026-11-21 P0-A test evidence (verified)
GitHub Actions run 44787989404 completed successfully with Debian real ISO + QEMU guest:
- LightDM logged into the AIWS Shell (not XFCE), Openbox served only as minimal WM, Chromium kiosk window was visible to X11.
- Selenium inside guest clicked AIWS file tree, opened a guest-only test file, created and dispatched a SQLite DAG task; the tool result reached completed.
- Guest serial emitted AIWS_GUI_BROWSER_PASS and AIWS_BOOT_SMOKE_PASS with shell=aiws gui=clicked. CI also captured a 1280x800 framebuffer showing the AIWS Workbench UI.
- This is the first P0-A GUI smoke acceptance, not a full production desktop quality gate (still needs native firmware ISO boot, long-running stability, IME/audio, accessibility, all functionality).
- Guest model is still deliberately not present in the ISO; the GUI confirmed its optional inactive state. Host access remains forbidden.


## 2026-11-21 unified control-plane milestone (in validation)
- GuestTaskStore now supports a central persistent DAG for guest read/write tools, guest-only systemd user operations (only model service may restart) and kernel candidate stage/verify/recovery_plan/abandon.
- Guest-local Qwen3.5-2B llama.cpp planner proposes **only read-only tools**; reviewed proposal can be saved as a pending SQLite DAG. No model may auto-approve/restart/mutate kernel.
- Restart recovery clears approval for interrupted write stages; audit hash chain validation fails closed before scheduling; singleton controller lock reduces duplicate live dispatch. The audit remains writable by the guest account and is NOT root-resistant attestation.
- Model registry accepts only guest-sourced GGUF with explicit SHA-256 and license declaration, tracks versioned hashes and allows previous guest model rollback while stopped; model weights and LoRA are NOT bundled, installed or trained.
- Kernel only has verified guest workspace config fragments and SHA256-pinned staged candidates; can abandon staging metadata but has **no live kernel installation, boot-slot switch, kernel signing or proven A/B rollback**.
- Real Debian/QEMU basic GUI click passed before the new kernel candidate test; new full candidate-flow QEMU run still pending at authoring. NixOS ISO remains eval-only, not built/booted.

All above lives inside a dedicated unprivileged guest. No guest agent API can control host files, root, host kernel, hypervisor, shared folders or host GPU.


## 2026-11-21 current real CI receipts (do not confuse builds with acceptance)

- Root cause of the earlier failed kernel candidate GUI test has been confirmed by QEMU runtime: durable stage was sent to ordinary toolplane and failed with "Unknown tool: kernel.stage". The persistent stage router was fixed and newer Debian/QEMU runs (e.g. 44849405506, 44849604994, 44849763444) succeeded.
- The first separate real OVMF EFI A/B attempt 44850151109 failed **before firmware startup** because the script's discovery code exited with no boot serial artifact. A robust code/vars/bootloader preflight has been committed; the **new real A/B run remains pending**. Never claim real boot fallback passed based only on the Python A/B manager tests.
- The first real Qwen3.5-2B Q4 CPU run 44850313856 verified pinned model download and compiled llama.cpp, but failed before inference because non-root Docker could not open its test script. Permissions were fixed. A subsequent real CPU + model-inclusive QEMU guest workflow is in progress, not yet a model performance proof.
- An independent unprivileged systemd Agent with private AF_UNIX IPC now owns persistent DAG state. The newer guest lifecycle smoke requires separate UI/Agent restarts, PID separation, task persistence and audit chain validity; that stricter new acceptance must pass before claiming long-term guest service reliability.
- The model-inclusive Debian ISO is **opt-in** and the default ISO remains without model weights. The guest model boot test is opt-in and must use a licensed SHA-verified builder artifact. A real 2B model in a networkless container, if passed, is still distinct from a real guest model test.

