# AIWS OS independent permission Broker / 独立权限决策架构

Status: **experimental same-UID application PDP**, not a mandatory OS
permission boundary. Code: os/runtime/aiws_permission_broker.py.

## 1. Architecture / 路径

AIWS React / optional local model
  -> localhost workbench API (CSRF, bounded requests)
  -> independent systemd user Agent over private AF_UNIX socket
  -> independent systemd user permission Broker over private AF_UNIX socket
  -> validated task tool (workspace/system service) -> audited task result.

Public MCP stdio is READ-ONLY and routes through Agent.tool.read then the
Broker. It cannot invoke file.replace, runtime.test, project.scaffold or
browser.snapshot. Kernel service/model mutations and file edits use reviewed
SQLite DAG steps and never a browser-provided approval Boolean.

Both units run as the **same unprivileged guest user**. Same-UID malware can
still modify SQLite, call low-level Python tools, invoke user commands or
impersonate local sockets. Treat this as defense in depth, **not** a
non-bypassable reference monitor, kernel policy, host isolation, or sandbox.

## 2. Permission query semantics

The request has exactly one of these operations:
- authorize_read: op/tool/arguments. Only a fixed eleven-tool read catalog
  plus guest system read operations are allowed. The tool schema is checked
  again; unknown and mutating tools are denied.
- authorize_stage: op/taskId/stageKey/tool/arguments. The Broker opens the
  guest Agent SQLite database *read-only* and checks the exact stage exists,
  is running, tool matches and arguments match the stored JSON; mutating
  tools also require stored approval=1. Browser-supplied approval fields are
  ignored because they are not accepted at all.

Every accepted execution attempt requires a matching durable stage.running
audit event; a separate 0600 SQLite ledger records the stage ID and the
corresponding run-event sequence. Duplicate authorization of the same
attempt is denied. A newly reviewed restarted attempt has a different
stage.running sequence. This ledger detects ordinary replay, **not** a
malicious same-UID writer altering both databases.

Coarse, configurable-in-code guardrails currently reject DAG definitions
with more than 8 mutating stages and reject execution when more than 24
mutating stages are queued/running/completed across all tasks within the
previous hour. These are conservative admission limits, not a formal
risk engine and not limits on user-issued shell commands outside the Agent.
They may need adjustment after real workload measurements.

Broker server rejects cross-UID peers using Linux SO_PEERCRED and uses
a 0700 runtime directory, a 0600 socket and bounded newline-framed JSON.
No network listener, subprocess tool, shell template or root escalation
exists in this policy process. Broker decisions log an opaque request hash,
allow status and reason code, not prompt or file contents.

## 3. Failure handling / 故障关闭

An absent, crashing or unresponsive Broker produces BrokerDenied in
the Agent: read calls fail and a durable running stage becomes failed
with error metadata; no fallback direct tool execution is permitted.
The web API exposes brokerReady, and guest boot/lifecycle acceptance
requires the independent unit healthy through UI and Agent restarts.

Broker unit: aiws-permission-broker.service, with NoNewPrivileges,
AF_UNIX-only address families, no network, memory and CPU quotas. The
Agent unit Requires + After it. The Broker may start before the Agent
SQLite database exists; reads remain scoped, write decisions deny until
the database is present and an approved stage is actually running.

## 4. Test contract

- os/verify/test_permission_broker.py: direct-read allowlist, unknown
  and direct-write refusal, persisted approval, running state, argument
  substitution, replay receipt, per-task write budget, cross-task rolling
  budget, UNIX IPC and Broker outage.
- os/verify/test_agent_service.py: live Agent + Broker test sockets,
  actual read-only tool routing and simulated Broker outage.
- os/verify/test_toolplane.py: public MCP does not expose or invoke writes.
- OS CI: service starts independently; brokerReady is true; real guest
  GUI/DAG lifecycle persists across Agent/UI restarts without replacing
  the Broker process.

A green Python static suite is not evidence of actual Linux MAC, process
separation or hostile-input isolation. Real QEMU and adversarial
isolation tests must be recorded separately.

## 5. Next security milestones (not shipped)

1. Separate Agent planner/user interface from execution worker under a
   distinct minimally privileged UID; avoid exposing the worker's socket
   to arbitrary user processes.
2. Store broker policy and approval authority outside the writable
   workspace, protect SQLite credentials, and remove same-UID DB
   forgery/bypass. Define scoped capabilities bound to workspace inode/
   mount identity, tool input digest, execution nonce, expiry and identity.
3. Enforce filesystem restrictions using openat2 resolution, Landlock,
   mount namespace and AppArmor as appropriate; enforce process creation
   and egress with OS controls rather than string filters.
4. Add explicit revocation/cancel, rollback, cumulative policy across
   tasks, failure injection and log integrity anchored outside the
   potentially compromised guest.
5. Test attempts to access host mounts, other users' files, network,
   process trees, system services, alternate IPC paths and malicious
   symlinks in a deliberately disposable VM. Do not assert unbypassable
   security until independently verified.

This Broker is a milestone toward the OS security architecture, not
a replacement for the hypervisor's guest/host isolation boundary.
