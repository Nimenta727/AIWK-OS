"""Guest-only, versioned, offline model weights: hash validation and rollback.

No downloads, model execution, host mounts, GPU passthrough, or arbitrary shell.
This validates artifact integrity and provenance *declarations*, not model safety.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

from aiws_guest_boundary import protect_guest_workspace, require_guest_runtime
from aiws_toolplane import _path

MODEL_ID = "Qwen/Qwen3.5-2B"
MAX_BYTES = 4 * 1024 * 1024 * 1024
DIGEST = re.compile(r"^[a-f0-9]{64}$")

class ModelArtifactError(ValueError):
    pass

def _sha256(file):
    h=hashlib.sha256()
    with Path(file).open("rb") as stream:
        while True:
            data=stream.read(1024*1024)
            if not data:
                break
            h.update(data)
    return h.hexdigest()

class GuestModelRegistry:
    def __init__(self, root, workspace, guard=None, runner=None):
        self.root=Path(root)
        self.workspace=Path(workspace).resolve(strict=True)
        self.guard=guard if guard is not None else require_guest_runtime
        self.runner=runner if runner is not None else subprocess.run

    def _ready(self):
        self.guard()
        protect_guest_workspace(self.workspace)
        if not self.root.is_absolute() or self.root.is_symlink():
            raise PermissionError("Guest model root must be an absolute directory, no symlinks")
        self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        if self.root.is_symlink() or self.root.stat().st_mode & 0o077:
            raise PermissionError("Guest model root must be private")
        protect_guest_workspace(self.root.resolve(strict=True))
        versions=self.root/"versions"
        versions.mkdir(mode=0o700,exist_ok=True)
        if versions.is_symlink() or versions.stat().st_mode & 0o077:
            raise PermissionError("Model versions must be private")
        return versions

    def _not_running(self):
        marker=Path.home()/".config/aiws/local-model-enabled"
        if marker.is_symlink() or marker.is_file():
            raise ModelArtifactError("Disable the guest model service before switching weights")
        result=self.runner(["systemctl","--user","is-active","--quiet",
                            "aiws-local-model.service"],
                           timeout=4,capture_output=True,check=False)
        if result.returncode == 0:
            raise ModelArtifactError("Guest model service still running")

    def _manifest(self):
        path=self.root/"registry.json"
        if path.is_symlink():
            raise ModelArtifactError("Model registry symlink refused")
        if not path.is_file():
            raise ModelArtifactError("No approved guest model artifact registered")
        try:
            data=json.loads(path.read_text(encoding="utf-8"))
        except (OSError,ValueError) as exc:
            raise ModelArtifactError("Model manifest damaged") from exc
        if not isinstance(data,dict) or data.get("modelId") != MODEL_ID or not isinstance(data.get("sha256"),str) or not DIGEST.fullmatch(data["sha256"]):
            raise ModelArtifactError("Invalid guest model manifest")
        return data

    def verify(self):
        self._ready()
        manifest=self._manifest()
        active=self.root/"aiws-local.gguf"
        version=self.root/"versions"/(manifest["sha256"]+".gguf")
        for path in (active,version):
            if path.is_symlink() or not path.is_file():
                raise ModelArtifactError("Model file missing or symlinked")
        if active.stat().st_size != version.stat().st_size or _sha256(active) != manifest["sha256"] or _sha256(version) != manifest["sha256"]:
            raise ModelArtifactError("Guest model artifact SHA-256 does not match registry")
        with active.open("rb") as stream:
            if stream.read(4) != b"GGUF":
                raise ModelArtifactError("Model artifact is not GGUF")
        return {"modelId": MODEL_ID,"sha256":manifest["sha256"],"verified":True,
                "weightsBytes":active.stat().st_size,"guestOnly":True,
                "licenseDeclared":manifest.get("licenseDeclared","not-verified")}

    def _activate(self, digest, previous):
        version=self.root/"versions"/(digest+".gguf")
        active=self.root/"aiws-local.gguf"
        if version.is_symlink() or not version.is_file():
            raise ModelArtifactError("Requested version is missing")
        if _sha256(version) != digest:
            raise ModelArtifactError("Refuse to activate a corrupted guest model version")
        handle,temp=tempfile.mkstemp(dir=self.root,prefix=".activate-")
        os.close(handle)
        os.unlink(temp)
        try:
            os.link(version,temp)
            os.replace(temp,active)
        finally:
            if os.path.lexists(temp):
                os.unlink(temp)
        record={"modelId":MODEL_ID,"sha256":digest,"previousSha256":previous,
                "licenseDeclared":"Apache-2.0 (source declaration; not independently audited)",
                "activatedAt":int(time.time()),"modelExecutionApproved":False}
        handle,temp=tempfile.mkstemp(dir=self.root,prefix=".manifest-")
        try:
            os.chmod(temp,0o600)
            with os.fdopen(handle,"w",encoding="utf-8") as output:
                json.dump(record,output,sort_keys=True)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temp,self.root/"registry.json")
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
        return self.verify()

    def import_guest(self, relative_path, expected_sha256, license_accepted=False):
        if not license_accepted:
            raise ModelArtifactError("Source model license declaration must be reviewed and accepted")
        if not isinstance(expected_sha256,str) or not DIGEST.fullmatch(expected_sha256):
            raise ModelArtifactError("A trusted exact SHA-256 is required")
        versions=self._ready()
        self._not_running()
        if not isinstance(relative_path,str) or not relative_path.endswith(".gguf"):
            raise ModelArtifactError("Only guest workspace .gguf artifact paths allowed")
        source=_path(self.workspace,relative_path)
        if source.is_symlink() or not source.is_file() or not 1024 <= source.stat().st_size <= MAX_BYTES:
            raise ModelArtifactError("Invalid guest GGUF size or file type")
        if _sha256(source) != expected_sha256:
            raise ModelArtifactError("Expected artifact hash does not match guest file")
        with source.open("rb") as stream:
            if stream.read(4) != b"GGUF":
                raise ModelArtifactError("Invalid GGUF signature")
        output=versions/(expected_sha256+".gguf")
        if output.is_symlink():
            raise ModelArtifactError("Model version symlink forbidden")
        if output.exists():
            if _sha256(output) != expected_sha256:
                raise ModelArtifactError("Existing model version hash conflict")
        else:
            fd,temp=tempfile.mkstemp(dir=versions,prefix=".import-")
            try:
                os.chmod(temp,0o600)
                with os.fdopen(fd,"wb") as dest, source.open("rb") as inp:
                    shutil.copyfileobj(inp,dest,length=1024*1024)
                    dest.flush()
                    os.fsync(dest.fileno())
                if _sha256(temp) != expected_sha256:
                    raise ModelArtifactError("Copied model hash differs from original")
                os.replace(temp,output)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)
        if (self.root/"registry.json").exists():
            previous=self._manifest()["sha256"]  # reject corrupted manifests
        else:
            previous=None
        return self._activate(expected_sha256,previous)

    def rollback(self, digest):
        if not isinstance(digest,str) or not DIGEST.fullmatch(digest):
            raise ModelArtifactError("Rollback requires exact candidate SHA-256")
        self._ready()
        self._not_running()
        current=self._manifest()["sha256"]
        if digest == current:
            raise ModelArtifactError("Requested model version is already active")
        return self._activate(digest,current)

def main():
    p=argparse.ArgumentParser(description="Verify/provision offline model within AIWS guest only")
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument("--verify",action="store_true")
    group.add_argument("--import-guest",metavar="RELATIVE_GGUF")
    group.add_argument("--rollback",metavar="SHA256")
    p.add_argument("--sha256")
    p.add_argument("--accept-source-license",action="store_true")
    args=p.parse_args()
    require_guest_runtime()
    workspace=Path(os.environ.get("AIWS_WORKSPACE",
                   str(Path.home()/".local/share/aiws/projects"))).resolve(strict=True)
    registry=GuestModelRegistry(Path.home()/".local/share/aiws/models",workspace)
    try:
        result=(registry.verify() if args.verify else
                registry.import_guest(args.import_guest,args.sha256,args.accept_source_license)
                if args.import_guest is not None else
                registry.rollback(args.rollback))
    except (PermissionError,OSError,ModelArtifactError) as exc:
        p.error(str(exc))
    print(json.dumps(result,sort_keys=True))

if __name__=="__main__":
    main()
