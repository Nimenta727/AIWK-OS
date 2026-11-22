"""Experimental guest-root-only systemd-boot A/B kernel trial manager.

Never called by an AI tool or HTTP endpoint. Requires an interactive guest
administrator, an actual EFI system partition and trusted hash-pinned kernel
and initrd. A remains the known-good default; B uses one-shot boot counting.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile
import time
from urllib.request import urlopen
from aiws_guest_boundary import _mounts, FORBIDDEN_FILESYSTEMS

DIGEST=re.compile(r"^[a-f0-9]{64}\Z")
RELEASE=re.compile(r"^[A-Za-z0-9._+-]{1,90}\Z")
NAME=re.compile(r"^[A-Za-z0-9._+-]{1,120}\Z")
TRIES=3
KNOWN_GOOD="aiws-A.conf"
TRY_ENTRY="aiws-B+3.conf"
BLESSED="aiws-B.conf"

class BootSlotError(ValueError):
    pass

def guest_root_guard():
    if os.geteuid()!=0:
        raise PermissionError("Boot slots require an interactive guest administrator")
    marker=Path("/etc/aiws/guest-managed")
    if marker.is_symlink() or not marker.is_file() or marker.read_text().strip()!="AIWS_GUEST_ONLY_VERSION=1":
        raise PermissionError("Not an AIWS guest image")
    if subprocess.run(["systemd-detect-virt","--vm","--quiet"],
                      capture_output=True,timeout=4).returncode:
        raise PermissionError("Boot manager cannot run outside a VM")

def filehash(path):
    sha=hashlib.sha256()
    with Path(path).open("rb") as source:
        while part:=source.read(1024*1024):
            sha.update(part)
    return sha.hexdigest()

def _atomic_file(dest,source):
    if dest.exists() or dest.is_symlink():
        raise BootSlotError("Refuse to overwrite an existing boot slot")
    handle,temp=tempfile.mkstemp(dir=dest.parent,prefix=".pending-")
    try:
        with os.fdopen(handle,"wb") as out:
            if isinstance(source,bytes):
                out.write(source)
            else:
                with Path(source).open("rb") as stream:
                    shutil.copyfileobj(stream,out,length=1024*1024)
            out.flush()
            os.fsync(out.fileno())
        if dest.exists() or dest.is_symlink():
            raise BootSlotError("Boot slot changed during staging")
        os.replace(temp,dest)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)

class BootSlots:
    def __init__(self,esp=Path("/boot"),inbox=Path("/var/lib/aiws/kernel-inbox"),
                 state=Path("/var/lib/aiws/boot-slots"),guard=None,runner=None,
                 mount_check=None):
        self.esp=Path(esp)
        self.inbox=Path(inbox)
        self.state=Path(state)
        self.guard=guard if guard is not None else guest_root_guard
        self.runner=runner if runner is not None else subprocess.run
        self.mount_check=mount_check

    def _ready(self):
        self.guard()
        for folder in (self.esp,self.inbox):
            if folder.is_symlink() or not folder.is_dir():
                raise BootSlotError("Boot or artifact directory is missing or symlinked")
        if self.mount_check is not None:
            self.mount_check(self.esp)
        else:
            esp=self.esp.resolve(strict=True)
            mounts=[(point,fs) for point,fs in _mounts() if point==esp]
            if len(mounts)!=1 or mounts[0][1].lower() not in ("vfat","msdos"):
                raise BootSlotError("A real mounted VFAT EFI system partition is required")
            if any(fs.lower() in FORBIDDEN_FILESYSTEMS for point,fs in _mounts()
                   if self.inbox.resolve(strict=True).is_relative_to(point)):
                raise BootSlotError("Kernel artifacts cannot originate in host/shared mount")
        self.state.mkdir(mode=0o700,parents=True,exist_ok=True)
        if self.state.is_symlink() or self.state.stat().st_mode & 0o077:
            raise BootSlotError("Boot slot state must be 0700")
        if not (self.esp/"loader/entries"/KNOWN_GOOD).is_file():
            raise BootSlotError("Known-good A boot entry missing; no safe fallback")

    def _bootctl(self,*args):
        # Fixed allowlist, no shell or user-selected executable.
        result=self.runner(["bootctl",*args],capture_output=True,
                           text=True,check=False,timeout=12)
        if result.returncode:
            raise BootSlotError("Guest systemd-boot operation failed: "+ " ".join(args))
        return result

    def stage(self,kernel,initrd,release,sha_kernel,sha_initrd):
        self._ready()
        if not RELEASE.fullmatch(release):
            raise BootSlotError("Invalid kernel release")
        files=[]
        for name,digest in ((kernel,sha_kernel),(initrd,sha_initrd)):
            if not isinstance(name,str) or not NAME.fullmatch(name) or not DIGEST.fullmatch(digest):
                raise BootSlotError("Only hash-pinned relative filenames allowed")
            path=self.inbox/name
            if path.is_symlink() or not path.is_file() or not 4096 <= path.stat().st_size <= 160*1024*1024:
                raise BootSlotError("Kernel or initrd file invalid")
            if filehash(path)!=digest:
                raise BootSlotError("Trusted boot artifact SHA-256 mismatch")
            files.append(path)
        entries=self.esp/"loader/entries"
        if (entries/TRY_ENTRY).exists() or (entries/BLESSED).exists():
            raise BootSlotError("B slot already staged or committed")
        slot=self.esp/"aiws/slot-b"
        if slot.exists() or slot.is_symlink():
            raise BootSlotError("B slot already present")
        original=(entries/KNOWN_GOOD).read_text(encoding="utf-8")
        options=next((x.removeprefix("options ").strip() for x in original.splitlines()
                      if x.startswith("options ")),None)
        if not options or any(not re.fullmatch(r"[A-Za-z0-9_.,/:=+@%~-]+",x)
                              for x in options.split()):
            raise BootSlotError("Known-good kernel command line unsafe")
        options=" ".join(x for x in options.split() if not x.startswith("aiws.slot="))
        slot.mkdir(mode=0o700,parents=True)
        _atomic_file(slot/"vmlinuz",files[0])
        _atomic_file(slot/"initrd",files[1])
        metadata={"slot":"B","status":"staged","release":release,
                  "kernelSha256":sha_kernel,"initrdSha256":sha_initrd,
                  "createdAt":int(time.time()),"tries":TRIES,
                  "knownGoodA":KNOWN_GOOD,"booted":False}
        _atomic_file(self.state/"candidate.json",
                     json.dumps(metadata,sort_keys=True).encode())
        content=("title AIWS candidate B\n"
                 "linux /aiws/slot-b/vmlinuz\n"
                 "initrd /aiws/slot-b/initrd\n"
                 "options "+options+" aiws.slot=B\n")
        _atomic_file(entries/TRY_ENTRY,content.encode())
        return metadata

    def _candidate(self):
        path=self.state/"candidate.json"
        if path.is_symlink() or not path.is_file():
            raise BootSlotError("No staged kernel B candidate")
        data=json.loads(path.read_text())
        if data.get("slot")!="B" or data.get("knownGoodA")!=KNOWN_GOOD:
            raise BootSlotError("Invalid B slot metadata")
        for name,sha in (("vmlinuz",data.get("kernelSha256")),
                         ("initrd",data.get("initrdSha256"))):
            if not isinstance(sha,str) or not DIGEST.fullmatch(sha):
                raise BootSlotError("Invalid candidate digest")
            path=self.esp/"aiws/slot-b"/name
            if path.is_symlink() or not path.is_file() or filehash(path)!=sha:
                raise BootSlotError("B slot artifact corrupted; refuse trial")
        return data

    def try_once(self):
        self._ready()
        data=self._candidate()
        if data["status"]!="staged" or not (self.esp/"loader/entries"/TRY_ENTRY).is_file():
            raise BootSlotError("B slot is not in untried state")
        self._bootctl("is-installed")
        self._bootctl("set-default",KNOWN_GOOD)
        self._bootctl("set-oneshot",TRY_ENTRY)
        return {"trialRequested":True,"knownGoodDefault":"A",
                "candidate":"B","tries":TRIES,"rebootPerformed":False}

    def rollback(self):
        self._ready()
        self._bootctl("is-installed")
        self._bootctl("set-default",KNOWN_GOOD)
        self._bootctl("set-oneshot",KNOWN_GOOD)
        return {"knownGoodDefault":"A","nextBoot":"A",
                "runningKernelChanged":False,"rebootPerformed":False}

    def commit_boot(self):
        self._ready()
        data=self._candidate()
        cmdline=Path("/proc/cmdline").read_text(encoding="ascii").split()
        if "aiws.slot=B" not in cmdline or platform.release()!=data["release"]:
            raise BootSlotError("Not currently running the verified B kernel")
        with urlopen("http://127.0.0.1:17640/api/v1/health",timeout=4) as response:
            health=json.load(response)
        if not (health.get("guestOnly") and health.get("agentIndependentService")
                and health.get("tasksPersistent") and health.get("uiBundled")):
            raise BootSlotError("AIWS Agent and UI have not passed guest boot health")
        if not (self.esp/"loader/entries"/BLESSED).is_file():
            self._bootctl("is-installed")
            self.runner(["systemd-bless-boot","good"],timeout=12,
                        capture_output=True,text=True,check=True)
        if not (self.esp/"loader/entries"/BLESSED).is_file():
            raise BootSlotError("systemd-boot has not blessed the kernel B entry")
        self._bootctl("set-default",BLESSED)
        data["status"]="committed"
        data["booted"]=True
        handle,temp=tempfile.mkstemp(dir=self.state,prefix=".committed-")
        try:
            with os.fdopen(handle,"w",encoding="utf-8") as out:
                json.dump(data,out,sort_keys=True)
                out.flush()
                os.fsync(out.fileno())
            os.replace(temp,self.state/"candidate.json")
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
        return {"default":"B","healthVerified":True,"kernelRelease":data["release"]}

def main():
    parser=argparse.ArgumentParser()
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--stage",action="store_true")
    group.add_argument("--try-b",action="store_true")
    group.add_argument("--commit-b",action="store_true")
    group.add_argument("--rollback-a",action="store_true")
    for key in ("kernel","initrd","release","kernel-sha","initrd-sha"):
        parser.add_argument("--"+key)
    parser.add_argument("--confirm-guest-root",action="store_true")
    args=parser.parse_args()
    if not args.confirm_guest_root:
        parser.error("Explicit interactive guest-root approval is required")
    mgr=BootSlots()
    try:
        if args.stage:
            result=mgr.stage(args.kernel,args.initrd,args.release,
                             args.kernel_sha,args.initrd_sha)
        elif args.try_b:
            result=mgr.try_once()
        elif args.commit_b:
            result=mgr.commit_boot()
        else:
            result=mgr.rollback()
    except (ValueError,PermissionError,OSError,subprocess.CalledProcessError) as exc:
        parser.error(str(exc))
    print(json.dumps(result,sort_keys=True))

if __name__=="__main__":
    main()
