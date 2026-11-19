"""Explicit, minimal subprocess integration; no credentials or general command runner."""
import platform
import shutil
import subprocess
from pathlib import Path

AGENTS = {"claude": "claude", "codex": "codex", "t3": "t3", "openclaw": "openclaw"}


def inventory():
    return {name: {"available": bool(shutil.which(cmd)), "binary": shutil.which(cmd) or ""}
            for name, cmd in AGENTS.items()}


def interactive(agent: str, project: Path):
    if agent not in AGENTS:
        raise ValueError("未知应用")
    if platform.system() != "Windows":
        raise OSError("交互式终端启动仅支持 Windows 来宾系统")
    binary = shutil.which(AGENTS[agent])
    if not binary:
        raise FileNotFoundError(f"{agent} 未安装或不在 PATH")
    # Use the resolved absolute binary: Windows cmd otherwise searches the project's
    # current directory first, allowing an untrusted repo to shadow codex/claude.
    subprocess.Popen(["cmd.exe", "/k", f'"{binary}"'], cwd=str(project),
                     creationflags=subprocess.CREATE_NEW_CONSOLE)
