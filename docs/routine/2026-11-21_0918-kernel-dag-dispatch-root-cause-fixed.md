# 2026-11-21 09:18 — Kernel DAG dispatch regression repair

## Root cause and code changes
The QEMU acceptance failures in 44795328720 occurred after file browsing and normal DAG execution. Code inspection found that `Controller._run_stage` still sent `kernel.stage` to the ordinary `toolplane.invoke` catalog, where it is unknown. The GuestOperations branch was accidentally inserted in the legacy `_execute` path and referenced an undefined `action`.

- Route persistent DAG guest system/kernel tools to `GuestOperations.execute(tool,args,approved=action["approvalGranted"])`; retain ordinary file/code tools in toolplane.invoke.
- The task store and guest operation layer independently enforce explicit approval for mutations; the legacy temporary job path remains limited to exposed ordinary tools.
- Add end-to-end HTTP DAG integration regression with a mocked guest kernel executor, and denial test for guest-only service operations without a VM marker.

## Files
os/runtime/aiws_workbench.py; os/verify/test_workbench.py; this routine.

## Validation and next steps
Need new OS static, Python/Windows, Debian ISO build and QEMU GUI approval receipt before declaring the failure fixed end-to-end. Continue service lifecycle integration, true kernel A/B boot recovery and real offline model inference measurements. No host API exposure.
