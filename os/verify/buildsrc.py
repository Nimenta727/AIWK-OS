"""Helper for static tests: the text of build.sh plus the runtime module paths it installs via os/runtime/MODULES."""
from pathlib import Path

OS = Path(__file__).resolve().parents[1]

def runtime_modules():
    return [l.strip() for l in (OS / "runtime/MODULES").read_text(encoding="utf-8").splitlines() if l.strip() and not l.lstrip().startswith("#")]

def build_text():
    manifest = "\n".join("os/runtime/" + m for m in runtime_modules())
    return (OS / "debian/build.sh").read_text(encoding="utf-8") + "\n# manifest:\n" + manifest + "\n"
