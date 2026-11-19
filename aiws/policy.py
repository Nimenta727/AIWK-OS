"""Explicit capability policy; a dashboard action never implies OS administrator access.

This describes implemented tool surfaces, not an OS-level sandbox. Real containment
requires a non-admin account, NTFS ACLs and an appropriately configured Codex sandbox.
"""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Capability:
    tier: str
    decision: str
    implemented: bool
    detail: str


CAPABILITIES = {
    "project_read": Capability("L1", "allowed", True, "Project-scoped metadata and task briefs"),
    "launch_official_cli": Capability("L2", "user_action", True, "Opens an official CLI in a visible console"),
    "git_worktree": Capability("L2", "confirmation", True, "Creates an isolated branch/worktree on demand"),
    "codex_readonly": Capability("L2", "approval", True, "Per-task approval, optional CLI worker, no write sandbox"),
    "project_write": Capability("L2", "not_exposed", False, "No generic file mutation endpoint"),
    "shell": Capability("L3", "not_exposed", False, "No arbitrary PowerShell/command endpoint"),
    "network_publish": Capability("L3", "not_exposed", False, "No push/email/upload endpoint"),
    "windows_gui": Capability("L3", "not_exposed", False, "No desktop control endpoint"),
    "system_admin": Capability("L3", "not_exposed", False, "No elevated process endpoint"),
}


def public_policy():
    return {key: asdict(value) for key, value in CAPABILITIES.items()}


def require(capability: str, *, confirmed: bool = False, approved: bool = False):
    item = CAPABILITIES.get(capability)
    if item is None or not item.implemented:
        raise ValueError("此操作未在安全工具网关开放")
    if item.decision == "confirmation" and confirmed is not True:
        raise ValueError("此操作需要单独确认")
    if item.decision == "approval" and approved is not True:
        raise ValueError("此操作需要有效的一次性审批")
