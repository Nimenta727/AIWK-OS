# 2026-11-21 12:00 — Verified independent guest Agent restart recovery and audit retention

## Actual acceptance
- GitHub real QEMU Debian guest run 44851455808: debian-image, nixos-evaluate and debian-boot all completed successfully.
- In-guest Selenium logged AIWS_GUI_BROWSER_PASS after file browsing, DAG stage execution, and explicit kernel candidate approval and staging; no kernel deployment took place.
- The same guest restarted the workbench user service without restarting the independent Agent, then restarted the Agent itself. It rechecked task IDs and audit chain, resulting in AIWS_GUEST_LIFECYCLE_PASS with agent_independent=true, agent_restart=true, audit_chain_valid=true, persistent_task_ids=2, ui_restart=true, host_access=false.
- The final guest serial AIWS_BOOT_SMOKE_PASS was emitted after all these tests; the failure of any gate would have suppressed this receipt.

## Documentation changes
Update docs/AIWS_OS_PRIORITY_GATES.md and docs/routine/README.md to distinguish this completed guest-level reliability proof from unresolved A/B firmware/kernel boot testing and actual 2B inference.

## Limitations and next steps
Full VM power-loss crash injection on a persistent disk, guest-root resistant audit signing, and real A/B recoverable kernel installation are not demonstrated. The separate Qwen3.5-2B Q4 runtime CI still needs an actual valid model response and metric receipt. Continue these without exposing host APIs.
