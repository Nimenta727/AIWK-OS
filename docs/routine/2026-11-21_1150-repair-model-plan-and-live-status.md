# 2026-11-21 11:50 — Restore local-model pending DAG endpoint and dynamic status

## Root cause and modifications
- GitHub static OS run 44851986840 failed one Python integration test because a previous service lifecycle refactor accidentally removed Controller.model_plan when replacing configure_model. The POST /api/v1/model/plan route remained, causing AttributeError/connection disconnect. Restore model_plan for both private systemd Agent production path and the embedded test path. Model plans are still **read-only, pending and never auto-dispatched**; the daemon independently validates the structured output and writes audit provenance.
- Fix LocalPlanner.status auto-enabled mode: read the guest user's service marker on every status request, not a stale bool captured at Controller startup. Explicit enabled=True/False test instances stay explicitly controlled.
- Add test_local_model.py dynamic enable → disable marker regression using a temporary fake HOME, no external model and only a loopback mock server.
- Update docs/routine/README.md for 11:35 and 11:44 changes plus this routine.

## Files
os/runtime/aiws_workbench.py, os/runtime/aiws_local_model.py, os/verify/test_local_model.py, docs/routine/README.md, this routine.

## Validation / next steps
Must pass OS static, Windows/Python, GUI and real QEMU systemd lifecycle. The real 2B still did not complete actual inference and A/B firmware fallback still lacks a pass; inspect actual CI evidence before claiming either done.
