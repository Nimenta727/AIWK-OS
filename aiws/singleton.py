"""One server/worker per workspace, using an OS-level advisory file lock."""
import os
from pathlib import Path


class WorkspaceLock:
    def __init__(self, workspace: Path):
        self.path = Path(workspace).resolve() / "aiws-instance.lock"
        self.fd = None

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = self.path.open("a+b")
        try:
            fd.seek(0)
            if os.name == "nt":
                import msvcrt
                if fd.tell() == 0 and self.path.stat().st_size == 0:
                    fd.write(b"0")
                    fd.flush()
                fd.seek(0)
                msvcrt.locking(fd.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, IOError) as exc:
            fd.close()
            raise RuntimeError("工作区已由另一个 AIWS 进程占用，请关闭旧工作台") from exc
        self.fd = fd
        return self

    def release(self):
        if self.fd is None:
            return
        try:
            if os.name == "nt":
                import msvcrt
                self.fd.seek(0)
                msvcrt.locking(self.fd.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fd.fileno(), fcntl.LOCK_UN)
        finally:
            self.fd.close()
            self.fd = None
