"""Guest-only AIWS OS policy guards.

Defense in depth: no API for the host or hypervisor. These guards are NOT a
hypervisor security proof and cannot contain a malicious guest root process.
"""
import os
from pathlib import Path
import re
import subprocess

MARKER = Path("/etc/aiws/guest-managed")
MARKER_CONTENT = "AIWS_GUEST_ONLY_VERSION=1"
FORBIDDEN_FILESYSTEMS = frozenset({
    "9p", "virtiofs", "vboxsf", "vmhgfs", "fuse.vmhgfs-fuse", "prl_fs",
    "cifs", "smb3", "nfs", "nfs4", "fuse.sshfs", "sshfs", "drvfs",
    "fuse.rclone", "fuse.gvfsd-fuse", "fuse.kio-fuse",
})
FORBIDDEN_PREFIXES = tuple(map(Path, (
    "/mnt", "/media", "/run/media", "/run/host", "/host", "/shared",
)))

def require_guest_runtime(marker=MARKER, detector=None):
    """Fail closed when accidentally started on bare-metal host or as root."""
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        raise PermissionError("AIWS Agent must never run as root")
    if not Path(marker).is_file() or Path(marker).is_symlink():
        raise PermissionError("AIWS guest image marker is missing")
    try:
        if Path(marker).read_text(encoding="ascii").strip() != MARKER_CONTENT:
            raise PermissionError("Invalid AIWS guest image marker")
    except (OSError, UnicodeError) as exc:
        raise PermissionError("Cannot validate AIWS guest marker") from exc
    # VM detection reduces accidental host execution; a guest root can spoof
    # evidence, so the hypervisor/host policy remains an independent boundary.
    cmd = detector or ["systemd-detect-virt", "--vm", "--quiet"]
    try:
        result = subprocess.run(cmd, timeout=4, capture_output=True, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PermissionError("VM verification unavailable") from exc
    if result.returncode != 0:
        raise PermissionError("AIWS Agent must run inside a dedicated virtual machine")
    return True

def _mounts(mountinfo=None):
    """List Linux mountpoints and filesystem types; never resolve or follow links."""
    if mountinfo is None:
        try:
            mountinfo = Path("/proc/self/mountinfo").read_text(encoding="utf-8")
        except OSError as exc:
            raise PermissionError("Cannot inspect guest mount topology") from exc
    result = []
    for line in mountinfo.splitlines():
        if " - " not in line:
            continue
        lhs, rhs = line.split(" - ", 1)
        left, right = lhs.split(), rhs.split()
        if len(left) < 5 or len(right) < 1:
            continue
        point = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), left[4])
        if point.startswith("/"):
            result.append((Path(point), right[0]))
    return result

def protect_guest_workspace(root, candidate=None, mountinfo=None):
    """Reject known host-sharing mounts and crossing into any nested mount.

    The workspace must already have been resolved and bounded by toolplane.
    """
    root = Path(root)
    target = Path(candidate) if candidate is not None else root
    if not root.is_absolute() or not target.is_absolute() or not target.is_relative_to(root):
        raise PermissionError("Workspace operation must remain inside guest workspace")
    for blocked in FORBIDDEN_PREFIXES:
        if root == blocked or root.is_relative_to(blocked):
            raise PermissionError("External/host mount location is not an AIWS guest workspace")
    mounts = _mounts(mountinfo)
    ancestors = [(point, fs) for point, fs in mounts if root == point or root.is_relative_to(point)]
    if not ancestors:
        raise PermissionError("Cannot identify guest workspace filesystem")
    deepest, fstype = max(ancestors, key=lambda item: len(item[0].parts))
    if fstype.lower() in FORBIDDEN_FILESYSTEMS:
        raise PermissionError("Host/remote/shared filesystem is not allowed")
    for point, fs in mounts:
        if point == deepest:
            continue
        if point.is_relative_to(root):
            raise PermissionError("Mounted filesystem under AIWS workspace is forbidden")
    return True
