"""AIWS guest-only system service and recoverable *candidate* kernel control.

No shell, host APIs, root access, live kernel change, reboot, package install,
module loading, bootloader editing, shared mount, or automatic deployment.
Mutations require the caller's separately audited DAG approval.
"""
from pathlib import Path
import hashlib
import json
import os
import platform
import re
import subprocess
import tempfile
import time
from uuid import uuid4

from aiws_guest_boundary import protect_guest_workspace, require_guest_runtime
from aiws_toolplane import _path
from aiws_model_registry import GuestModelRegistry

READ_TOOLS = frozenset({"service.inspect", "kernel.inspect", "kernel.verify", "kernel.recovery_plan"})
WRITE_TOOLS = frozenset({"service.restart", "service.enable", "service.disable", "kernel.stage", "kernel.abandon"})
TOOLS = READ_TOOLS | WRITE_TOOLS
SERVICES = frozenset({"aiws-workbench.service", "aiws-local-model.service"})
RESTARTABLE = frozenset({"aiws-local-model.service"})
FRAGMENT_KEYS = frozenset({
    "CONFIG_VIRTIO", "CONFIG_VIRTIO_PCI", "CONFIG_VIRTIO_BLK",
    "CONFIG_VIRTIO_NET", "CONFIG_VIRTIO_CONSOLE", "CONFIG_VIRTIO_RNG",
    "CONFIG_DRM_VIRTIO_GPU", "CONFIG_CGROUPS", "CONFIG_CGROUP_BPF",
    "CONFIG_NAMESPACES", "CONFIG_OVERLAY_FS", "CONFIG_SECURITY_APPARMOR",
    "CONFIG_SECURITY_LANDLOCK", "CONFIG_SECCOMP", "CONFIG_SECCOMP_FILTER",
    "CONFIG_AUDIT", "CONFIG_BPF_SYSCALL", "CONFIG_BPF_JIT", "CONFIG_KVM_GUEST"
})
SPEC = {
    "service.inspect": ("service",),
    "service.restart": ("service",),
    "service.enable": ("service",),
    "service.disable": ("service",),
    "kernel.inspect": (),
    "kernel.stage": ("path", "expectedSha256"),
    "kernel.verify": ("candidateId",),
    "kernel.recovery_plan": ("candidateId",),
    "kernel.abandon": ("candidateId",),
}

def catalog():
    return [{"name": name, "description": "Guest-only service/kernel candidate operation: " + name,
             "inputSchema": {"type": "object", "properties": {k: {"type": "string"} for k in fields},
                             "required": list(fields), "additionalProperties": False}}
            for name, fields in sorted(SPEC.items())]


class GuestOperationError(ValueError):
    pass

def validate(tool, args):
    if tool not in SPEC or not isinstance(args, dict) or set(args) != set(SPEC[tool]):
        raise GuestOperationError("Unsupported guest operation or unexpected arguments")
    if any(not isinstance(v, str) or not v or len(v) > 512 for v in args.values()):
        raise GuestOperationError("Guest operation arguments must be bounded strings")
    if "service" in args:
        names = RESTARTABLE if tool in ("service.restart", "service.enable", "service.disable") else SERVICES
        if args["service"] not in names:
            raise GuestOperationError("Service not in guest-only allowlist")
    if "candidateId" in args and not re.fullmatch(r"[0-9a-f]{32}", args["candidateId"]):
        raise GuestOperationError("Invalid candidate ID")
    if "path" in args:
        target = Path(args["path"])
        if (target.is_absolute() or ".." in target.parts or "\\" in args["path"]
                or target.suffix != ".fragment" or ".git" in target.parts or ".ssh" in target.parts):
            raise GuestOperationError("Kernel fragment must be a guest project relative .fragment file")
        if not re.fullmatch("[0-9a-f]{64}", args["expectedSha256"]):
            raise GuestOperationError("Candidate requires an exact original SHA-256")
    return True

def _fragment_validate(data):
    if len(data) > 16384:
        raise GuestOperationError("Kernel fragment is over 16 KiB")
    try:
        content = data.decode("ascii")
    except UnicodeError as exc:
        raise GuestOperationError("Kernel fragment must be ASCII") from exc
    seen = set()
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"(CONFIG_[A-Z0-9_]+)=(y|m|n)", line)
        if not match or match[1] not in FRAGMENT_KEYS or match[1] in seen:
            raise GuestOperationError("Unsafe, duplicate or invalid kernel config entry")
        seen.add(match[1])
    if not seen:
        raise GuestOperationError("Kernel fragment contains no allowed config entries")
    return len(seen)

def _atomic_private(path, data):
    if path.is_symlink() or path.exists():
        raise GuestOperationError("Immutable candidate file already exists")
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".pending-")
    try:
        os.chmod(temp, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists() or path.is_symlink():
            raise GuestOperationError("Candidate raced with a different writer")
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)

class GuestOperations:
    def __init__(self, workspace, state, guard=None, runner=None):
        self.workspace = Path(workspace).resolve(strict=True)
        self.state = Path(state)
        self.guard = guard if guard is not None else require_guest_runtime
        self.runner = runner if runner is not None else subprocess.run

    def _ready(self):
        self.guard()
        protect_guest_workspace(self.workspace)
        if not self.state.is_absolute() or self.state.is_symlink():
            raise PermissionError("Guest candidate state must be an absolute, non-symlink folder")
        self.state.mkdir(parents=True, mode=0o700, exist_ok=True)
        if self.state.is_symlink() or self.state.stat().st_mode & 0o077:
            raise PermissionError("Guest candidate state must be private (0700)")
        protect_guest_workspace(self.state.resolve(strict=True))

    def _candidate(self, candidate_id):
        directory = self.state
        meta_path, file_path = directory / (candidate_id + ".json"), directory / (candidate_id + ".fragment")
        for path in (meta_path, file_path):
            if path.is_symlink() or not path.is_file():
                raise GuestOperationError("Unknown or unsafe kernel candidate")
        try:
            meta = json.loads(meta_path.read_text(encoding="ascii"))
            data = file_path.read_bytes()
        except (OSError, ValueError) as exc:
            raise GuestOperationError("Kernel candidate metadata unavailable") from exc
        digest = hashlib.sha256(data).hexdigest()
        if not isinstance(meta, dict) or meta.get("id") != candidate_id or meta.get("sha256") != digest:
            raise GuestOperationError("Kernel candidate hash mismatch; stop and review")
        _fragment_validate(data)
        return meta, meta_path, digest

    def execute(self, tool, args, *, approved=False):
        validate(tool, args)
        if tool in WRITE_TOOLS and not approved:
            raise PermissionError("Explicitly approved guest DAG stage required")
        self._ready()
        if tool == "service.inspect":
            command = ["systemctl", "--user", "show", "--no-pager",
                       "--property=LoadState,ActiveState,SubState,UnitFileState",
                       args["service"]]
            result = self.runner(command, capture_output=True, text=True,
                                 check=False, timeout=5)
            if result.returncode:
                raise GuestOperationError("Guest user service status unavailable")
            result_pairs = {}
            for line in result.stdout[:4096].splitlines():
                key, sep, value = line.partition("=")
                if sep and key in ("LoadState", "ActiveState", "SubState", "UnitFileState"):
                    result_pairs[key] = value[:64]
            return {"service": args["service"], "scope": "guest-user",
                    "status": result_pairs}
        if tool == "service.restart":
            result = self.runner(["systemctl", "--user", "restart",
                                  "aiws-local-model.service"], capture_output=True,
                                 text=True, check=False, timeout=12)
            if result.returncode:
                raise GuestOperationError("Guest local model restart failed")
            return {"service": "aiws-local-model.service", "restartRequested": True,
                    "hostTouched": False, "privileged": False}
        if tool in ("service.enable", "service.disable"):
            # This is the ONLY production path to mutate local model service
            # state; it is a separately approved durable guest DAG stage.
            enable = tool == "service.enable"
            if enable:
                registry=GuestModelRegistry(Path.home()/".local/share/aiws/models",
                                            self.workspace)
                if Path("/usr/local/share/aiws/model-preload/manifest.json").is_file():
                    registry.import_bundled(verify_only=True)
                else:
                    registry.verify()
            flag_dir=Path.home()/".config/aiws"
            flag_dir.mkdir(mode=0o700,parents=True,exist_ok=True)
            if (flag_dir.is_symlink() or
                not flag_dir.resolve().is_relative_to(Path.home().resolve()) or
                flag_dir.stat().st_mode & 0o077):
                raise GuestOperationError("Model service flag directory must be private")
            flag=flag_dir/"local-model-enabled"
            if flag.is_symlink():
                raise GuestOperationError("Model service flag symlink forbidden")
            action="enable" if enable else "disable"
            result=self.runner(["systemctl","--user",action,"--now",
                                "aiws-local-model.service"],
                               capture_output=True,text=True,
                               check=False,timeout=20)
            if result.returncode:
                raise GuestOperationError("Approved guest model service change failed")
            if enable:
                flag.write_text("1\n",encoding="ascii")
                os.chmod(flag,0o600)
            else:
                flag.unlink(missing_ok=True)
            return {"service":"aiws-local-model.service",
                    "enabled":enable,"guestOnly":True,"approved":True,
                    "privileged":False}
        if tool == "kernel.inspect":
            return {"runningKernel": platform.release(), "guestOnly": True,
                    "kernelDeploymentSupported": False, "candidateOnly": True,
                    "note": "No live kernel, bootloader or host access"}
        if tool == "kernel.stage":
            source = _path(self.workspace, args["path"])
            if not source.is_file() or source.is_symlink():
                raise GuestOperationError("Kernel fragment must be a regular guest file")
            data = source.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            if digest != args["expectedSha256"]:
                raise GuestOperationError("Kernel fragment changed since approval")
            lines = _fragment_validate(data)
            if len(list(self.state.glob("*.json"))) >= 32:
                raise GuestOperationError("Guest kernel staging quota exceeded")
            candidate_id = uuid4().hex
            receipt = {"id": candidate_id, "status": "staged", "sha256": digest,
                       "runningKernel": platform.release(), "entries": lines,
                       "createdAt": int(time.time()), "sourcePath": args["path"],
                       "deployed": False, "bootRecoveryReady": False}
            _atomic_private(self.state / (candidate_id + ".fragment"), data)
            _atomic_private(self.state / (candidate_id + ".json"),
                            json.dumps(receipt, sort_keys=True).encode("ascii"))
            return receipt
        if tool in ("kernel.verify", "kernel.recovery_plan", "kernel.abandon"):
            meta, location, digest = self._candidate(args["candidateId"])
            if tool == "kernel.verify":
                return {"id": meta["id"], "sha256": digest, "integrity": "verified",
                        "status": meta["status"], "deployed": False}
            if tool == "kernel.recovery_plan":
                return {"candidateId": meta["id"], "sha256": digest,
                        "knownRunningKernel": meta["runningKernel"],
                        "candidateStatus": meta["status"],
                        "stagedArtifactRecoverable": True, "bootRecoveryReady": False,
                        "bootSlotSwitchAllowed": False, "manualIndependentVMBackupRequired": True,
                        "note": "This is an audited rollback plan for staging only, NOT kernel boot recovery"}
            if meta["status"] != "staged":
                raise GuestOperationError("Only staged candidates may be abandoned")
            updated = dict(meta, status="abandoned", abandonedAt=int(time.time()))
            # Only metadata may change; source snapshot remains immutable.
            fd, temporary = tempfile.mkstemp(dir=self.state, prefix=".status-")
            try:
                os.chmod(temporary, 0o600)
                with os.fdopen(fd, "w", encoding="ascii") as out:
                    json.dump(updated, out, sort_keys=True)
                    out.flush()
                    os.fsync(out.fileno())
                if location.is_symlink():
                    raise GuestOperationError("Candidate metadata became a symlink")
                os.replace(temporary, location)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            return {"candidateId": meta["id"], "status": "abandoned",
                    "kernelModified": False, "snapshotRetained": True}
        raise GuestOperationError("Unsupported guest operation")
