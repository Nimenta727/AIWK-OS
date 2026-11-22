#!/usr/bin/env python3
"""Work disk (second virtual disk) setup and snapshots. Guest only, runs as root from a systemd unit at boot.

The system lives on the read-only live image; everything the AI works on lives on a SEPARATE disk labelled AIWS-WORK:
  * mounted noexec,nodev,nosuid  -> nothing placed there by the AI can be executed from it;
  * btrfs, work files in the subvolume `work`, read-only snapshots in `.snapshots` -> one-step rollback.
Safety rules (each one tested):
  * format ONLY a disk that is a whole, unmounted, unpartitioned disk with no filesystem signature and no label, and only when
    exactly one such disk exists; a disk with any signature, a partition table, or a different label is never touched;
  * re-check with blkid immediately before formatting;
  * snapshot names are generated or strictly validated; rollback keeps the old state as a snapshot first.
All system effects go through an injectable `run`, so the decision logic is tested without a disk.
"""
import json
import re
import subprocess
import sys
import time

LABEL = "AIWS-WORK"
MOUNT = "/srv/aiws-work"
MIN_SIZE = 1 << 30
SNAP_LABEL = re.compile(r"[a-z0-9][a-z0-9-]{0,23}\Z")
SNAP_NAME = re.compile(r"^[0-9]{8}T[0-9]{6}Z(-[a-z0-9][a-z0-9-]{0,23})?\Z")
DEV_NAME = re.compile(r"^/dev/[A-Za-z0-9]{2,16}\Z")
MOUNT_OPTS = "noexec,nodev,nosuid,noatime,compress=zstd"
KEEP_SNAPSHOTS = 20


class DiskError(Exception):
    pass


def _flat(devices):
    for d in devices:
        yield d
        yield from _flat(d.get("children") or [])


def plan(lsblk, label=LABEL):
    """lsblk = parsed `lsblk -J -b -o NAME,PATH,TYPE,FSTYPE,LABEL,SIZE,MOUNTPOINTS,RM,RO`. Returns (action, device, reason)."""
    devs = list(_flat(lsblk.get("blockdevices", [])))
    labelled = [d for d in devs if d.get("label") == label]
    if len(labelled) > 1:
        return "refuse", None, "more than one device is labelled " + label
    if labelled:
        d = labelled[0]
        if d.get("fstype") != "btrfs":
            return "refuse", d.get("path"), "a device labelled %s has filesystem %r, not btrfs; not touching it" % (label, d.get("fstype"))
        return "mount", d.get("path"), "existing work disk"
    blank = []
    for d in lsblk.get("blockdevices", []):
        mps = [m for m in (d.get("mountpoints") or []) if m]
        if (d.get("type") == "disk" and not d.get("children") and not d.get("fstype") and not d.get("label") and not mps
                and not d.get("rm") and int(d.get("size") or 0) >= MIN_SIZE and not d.get("ro")):
            blank.append(d)
    if len(blank) == 1:
        return "format", blank[0].get("path"), "one blank disk"
    if not blank:
        return "none", None, "no work disk attached"
    return "refuse", None, "several blank disks; attach exactly one work disk"


def _check_dev(dev):
    if not isinstance(dev, str) or not DEV_NAME.match(dev):
        raise DiskError("unsafe device name")


def _run(run, argv, **kw):
    code, out, err = run(argv, **kw)
    if code != 0:
        raise DiskError("%s failed: %s" % (argv[0], (err or out or "").strip()[:160]))
    return out


def apply(action, dev, run):
    """Carry out a plan. `run(argv)` -> (code, stdout, stderr)."""
    if action in ("none",):
        return "no work disk"
    if action == "refuse":
        raise DiskError("refusing: nothing was changed")
    _check_dev(dev)
    if action == "format":
        code, out, _ = run(["blkid", "-p", dev])           # exit 2 and no output = no signature at all
        if code != 2 or out.strip():
            raise DiskError("device is no longer blank; not formatting")
        _run(run, ["mkfs.btrfs", "-L", LABEL, dev])
    _run(run, ["mkdir", "-p", MOUNT])
    _run(run, ["mount", "-t", "btrfs", "-o", MOUNT_OPTS, dev, MOUNT])
    for sub in ("work", ".snapshots"):
        code, _, _ = run(["btrfs", "subvolume", "show", MOUNT + "/" + sub])
        if code != 0:
            _run(run, ["btrfs", "subvolume", "create", MOUNT + "/" + sub])
    return "mounted " + dev


# ---- snapshots ----
def new_name(label="", clock=time.gmtime):
    if label and not SNAP_LABEL.match(label):
        raise DiskError("invalid snapshot label")
    stamp = time.strftime("%Y%m%dT%H%M%SZ", clock())
    name = stamp + ("-" + label if label else "")
    if not SNAP_NAME.match(name):
        raise DiskError("invalid snapshot label")
    return name


def list_snapshots(run):
    out = _run(run, ["ls", "-1", MOUNT + "/.snapshots"])
    return sorted((n for n in out.split("\n") if SNAP_NAME.match(n)), reverse=True)


def snapshot(run, label="", clock=time.gmtime):
    name = new_name(label, clock)
    _run(run, ["btrfs", "subvolume", "snapshot", "-r", MOUNT + "/work", MOUNT + "/.snapshots/" + name])
    for old in list_snapshots(run)[KEEP_SNAPSHOTS:]:      # prune the oldest; names were validated by list_snapshots
        _run(run, ["btrfs", "subvolume", "delete", MOUNT + "/.snapshots/" + old])
    return name


def rollback(run, name, clock=time.gmtime):
    """Restore `work` from a snapshot. The current state is kept as a snapshot first, so a rollback can itself be undone."""
    if not SNAP_NAME.match(name or "") or name not in list_snapshots(run):
        raise DiskError("no such snapshot")
    keep = snapshot(run, "pre-rollback", clock)
    _run(run, ["btrfs", "subvolume", "delete", MOUNT + "/work"])
    _run(run, ["btrfs", "subvolume", "snapshot", MOUNT + "/.snapshots/" + name, MOUNT + "/work"])   # writable copy
    return keep


def _real_run(argv, **kw):
    p = subprocess.run(argv, capture_output=True, text=True, timeout=120, shell=False)
    return p.returncode, p.stdout, p.stderr


def main(argv=None):
    argv = argv or sys.argv[1:]
    import os
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        sys.exit("must run as root (systemd unit)")
    cmd = argv[0] if argv else "setup"
    try:
        if cmd == "setup":
            code, out, err = _real_run(["lsblk", "-J", "-b", "-o", "NAME,PATH,TYPE,FSTYPE,LABEL,SIZE,MOUNTPOINTS,RM,RO"])
            if code != 0:
                sys.exit("lsblk failed")
            action, dev, why = plan(json.loads(out))
            print("work disk:", action, dev or "", "-", why)
            print(apply(action, dev, _real_run))
        elif cmd == "snapshot":
            print(snapshot(_real_run, argv[1] if len(argv) > 1 else ""))
        elif cmd == "list":
            print("\n".join(list_snapshots(_real_run)))
        elif cmd == "rollback" and len(argv) == 2:
            print("kept current state as", rollback(_real_run, argv[1]))
        else:
            sys.exit("usage: setup | snapshot [label] | list | rollback NAME")
    except DiskError as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
