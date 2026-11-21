# 2026-11-21 13:30 — 独立 Broker PDP 与统一 Agent/MCP 策略闭环

## Actual changes / 实装范围

1. Introduced aiws_permission_broker.py with private UNIX peer-credential
   checks and a separate systemd-user Broker unit/launcher. No root rights,
   network listener or host access is supplied.
2. Agent task dispatch now consults Broker for **every** persisted running
   stage before executing any tool. Direct Agent read IPC also consults it.
   Browser-provided booleans cannot directly satisfy Broker approval:
   it checks SQLite state/tool/arguments/approval and durable stage.running.
3. Added a private persisted single-use execution-receipt ledger, per-DAG
   maximum 8 mutating stages, and rolling 24 recent write-stage budget.
   Broker failure marks stages failed and denies direct reads. A health field
   now reports Broker status and same-UID policy scope.
4. Changed the guest MCP stdio public catalog to READ-ONLY, routing calls
   through live Agent/Broker IPC. Low-level tools are retained for
   controlled DAG execution; users cannot invoke writes via MCP itself.
5. Bundled Broker Python, binary launcher and user systemd unit in Debian
   ISO; Agent Requires/After Broker; guest boot/lifecycle checks and React
   overview now expose actual Broker status.
6. Added explicit standalone Broker tests, Agent socket integration tests,
   MCP bypass-denial test and expanded static build/security contracts.
7. Fixed the previous static test false positive: the forbidden -kernel
   pattern appeared only in a firmware script comment, not its invocation.
8. Updated the Tool Fabric documentation to match the new read-only MCP
   contract; added broker threat model and production-gates references.

## Files / affected areas

- os/runtime/{aiws_permission_broker.py,aiws_agent_service.py,aiws_workbench.py,aiws_mcp.py}
- os/debian/build.sh, os/debian/config/includes.chroot/etc/systemd/user/
  {aiws-permission-broker.service,aiws-agent.service}, os/debian/config/includes.chroot/
  usr/local/bin/{aiws-broker,aiws-boot-smoke}
- os/verify/{test_permission_broker.py,test_agent_service.py,test_toolplane.py,
  test_config.py,aiws_guest_lifecycle_smoke.py}
- desktop/AIWorkstation.Frontend/src/os/OsWorkbench.tsx
- .github/workflows/aiws-os-static.yml
- README, os/README, docs/README, docs/AIWS_OS_PRODUCTION_GATES,
  docs/AIWS_AGENT_TOOL_FABRIC, docs/AIWS_PERMISSION_BROKER and this routine log.

## Verification / 验证现状

- Previous firmware/Shell commit static job failed on a test-only assertion
  mistakenly matching a comment; actual full prior run had otherwise passed.
  This commit corrects the assertion.
- New broker integration/CI and full BIOS/UEFI firmware are **unverified
  until CI finishes**. Do not label them accepted in advance.
- Same-UID Broker is not a mandatory security boundary. Guest root or
  malicious processes holding the Agent user UID can bypass these
  application-level checks and alter the SQLite ledger.
- No physical hardware, installer, MAC/LSM escape, TPM or privileged
  production sandbox acceptance is asserted.

## Next / 下一步

1. Inspect OS static, Python/Windows, real 2B, QEMU direct and both firmware
   matrix jobs for this exact commit. Repair failures with new routine logs.
2. Move actual tool execution behind distinct low-privilege Linux worker
   credentials/LSM policy; test non-bypass and revocation independently.
3. Continue Shell app lifecycle/CJK IME/notifications and physical
   firmware acceptance; preserve model held-out evaluation and safe
   Windows→Linux audit-history migration.
