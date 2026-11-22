"""Where the DeepSeek API key lives, and the rules for touching it.

* A private file in the guest user's config directory (default ~/.config/aiws/deepseek.key), mode 0600, owned by the user,
  a regular file (no symlink), small. Never inside the workspace, the repository, task data or the event store (project rule 6).
* The environment variable DEEPSEEK_API_KEY is accepted as a source for developers; the file wins when both exist.
* The key is read by the supervisor and handed to the runner over a pipe: never in argv, never in the child's environment.
* The UI can learn only: configured yes/no, where from, the last 4 characters; it can set or clear it, never read it back.
"""
import os
import re
import stat
from pathlib import Path

KEY_RE = re.compile(r"[A-Za-z0-9_.\-]{8,256}\Z")
MAX_FILE = 512


class SecretError(Exception):
    pass


def default_path():
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "aiws" / "deepseek.key"


def _check_file(path):
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        raise SecretError("The key file must be a regular file, not a link")
    if st.st_uid != os.getuid():
        raise SecretError("The key file must belong to this user")
    if st.st_mode & 0o077:
        raise SecretError("The key file must not be readable by others (use mode 600)")
    if st.st_size > MAX_FILE:
        raise SecretError("The key file is too large")


def load(path=None, environ=None):
    """Return the key or None. Raises SecretError for an unsafe file (so a bad file is never silently ignored)."""
    path = Path(path) if path else default_path()
    try:
        _check_file(path)
    except FileNotFoundError:
        env = (environ if environ is not None else os.environ).get("DEEPSEEK_API_KEY", "").strip()
        return env if KEY_RE.match(env) else None
    key = path.read_text(encoding="utf-8").strip()
    if not KEY_RE.match(key):
        raise SecretError("The key file does not contain a valid key")
    return key


def status(path=None, environ=None):
    path = Path(path) if path else default_path()
    try:
        key = load(path, environ)
    except SecretError as exc:
        return {"configured": False, "source": None, "last4": None, "problem": str(exc)}
    except OSError:
        return {"configured": False, "source": None, "last4": None, "problem": "The key file could not be read"}
    if key is None:
        return {"configured": False, "source": None, "last4": None, "problem": None}
    return {"configured": True, "source": "file" if path.exists() else "env", "last4": key[-4:], "problem": None}


def save(key, path=None, forbidden_roots=()):
    path = Path(path) if path else default_path()
    if not isinstance(key, str) or not KEY_RE.match(key.strip()):
        raise SecretError("That does not look like an API key")
    for root in forbidden_roots:                       # never inside the workspace (or any other place the AI can read as data)
        try:
            if Path(os.path.realpath(path.parent)).is_relative_to(os.path.realpath(root)):
                raise SecretError("The key cannot be stored inside the workspace")
        except ValueError:
            pass
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise SecretError("The config directory must not be a link")
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.unlink()
    except FileNotFoundError:
        pass
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(key.strip() + "\n")
    os.replace(tmp, path)
    return status(path, {})


def clear(path=None):
    path = Path(path) if path else default_path()
    try:
        _check_file(path)
        path.unlink()
    except FileNotFoundError:
        pass
    return status(path, {})
