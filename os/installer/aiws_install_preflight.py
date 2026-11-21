#!/usr/bin/env python3
"""Read-only AIWS OS installation preflight. NEVER partitions or writes disks.

Installation is intentionally blocked until an independently verified,
interactive disk selection and rollback implementation is available.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

MIN_BYTES = 32 * 1024**3
DEVICE = re.compile(r"^/dev/(?:vd[a-z]+|sd[a-z]+|nvme\d+n\d+)$")

def inspect_devices(lsblk):
    """Only whole, non-removable disks with a complete lsblk report."""
    if not isinstance(lsblk, dict) or not isinstance(lsblk.get("blockdevices"), list):
        raise ValueError("Invalid lsblk JSON")
    result = []
    for item in lsblk["blockdevices"]:
        if not isinstance(item, dict):
            continue
        name, size = item.get("path"), item.get("size")
        if (item.get("type") != "disk" or not isinstance(name, str)
                or not DEVICE.fullmatch(name) or not isinstance(size, int)
                or isinstance(size, bool) or size < MIN_BYTES):
            continue
        if str(item.get("rm", "1")) not in ("0", "False", "false"):
            continue
        # A disk already holding partitions or mountpoints must never be
        # presented as a candidate by this read-only preflight.
        if item.get("children") or item.get("mountpoint") or item.get("mountpoints"):
            continue
        result.append({"device": name, "sizeBytes": size,
                       "model": str(item.get("model") or "")[:80]})
    return result

def inspect_environment():
    virtualization = subprocess.run(
        ["systemd-detect-virt", "--vm", "--quiet"], check=False,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    firmware = Path("/sys/firmware/efi").is_dir()
    report = {"schemaVersion": 1, "installerAvailable": False,
              "diskWritesPerformed": False,
              "firmware": "UEFI" if firmware else "BIOS",
              "virtualMachineDetected": virtualization.returncode == 0,
              "candidateBlankDisks": [], "blockers": []}
    if not report["virtualMachineDetected"]:
        report["blockers"].append("VM-only prototype: physical installation disabled")
    if not firmware:
        report["blockers"].append("UEFI firmware required for first install milestone")
    try:
        raw = subprocess.run(
            ["lsblk", "--json", "--bytes", "--output",
             "PATH,TYPE,SIZE,RM,MOUNTPOINT,MODEL"],
            check=True, capture_output=True, text=True, timeout=10)
        report["candidateBlankDisks"] = inspect_devices(json.loads(raw.stdout))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        report["blockers"].append("Cannot safely enumerate disks: " + type(exc).__name__)
    report["blockers"].append(
        "Installer and recovery are NOT implemented; no disk will be modified")
    return report

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="machine-readable read-only report")
    parser.add_argument("--install", action="store_true",
                        help="explicitly refused until installer safety gates pass")
    args = parser.parse_args(argv)
    if args.install:
        print("REFUSED: no verified installer, snapshot or rollback implementation", file=sys.stderr)
        return 3
    report = inspect_environment()
    print(json.dumps(report, indent=2, ensure_ascii=False) if args.json else
          "AIWS OS installation preflight (READ ONLY)\n" +
          "\n".join(report["blockers"]) +
          "\nCandidate blank VM disks: " + str(len(report["candidateBlankDisks"])))
    return 0

if __name__ == "__main__":
    sys.exit(main())
