"""Explicit, minimal subprocess integration; no credentials or general command runner."""
import os
import platform
import shutil
import subprocess
import threading
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


def codex_readonly(task, store):
    """Opt-in read-only analysis only; stdin avoids Windows npm .cmd argument injection."""
    if platform.system() != "Windows":
        raise OSError("自动执行只在 Windows 来宾系统中支持")
    binary = shutil.which("codex")
    if not binary:
        raise FileNotFoundError("Codex CLI 不在 PATH")
    project = store.project_path(task["project"])
    if not (project / ".git").exists():
        raise ValueError("自动 Codex 执行要求项目已初始化 Git；避免跳过项目检查")
    if task["status"] == "running":
        raise ValueError("任务已运行")
    store.update(task["id"], "running")
    store.audit("codex_run_started", {"id":task["id"], "mode":"read-only"})
    prompt = (f"任务：{task['title']}\n\n{task['description']}\n\n"
              "请只读分析当前仓库并给出建议。不要修改文件，不要推送代码，"
              "不要执行安装或系统配置。将建议用中文输出。")

    def worker():
        try:
            # codex exec - consumes prompt via stdin. Keep arguments constant (no shell command injection).
            proc = subprocess.Popen([binary, "exec", "--sandbox", "read-only",
                                     "--ephemeral", "-"], cwd=str(project),
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True,
                                    encoding="utf-8", errors="replace")
            try:
                out, _ = proc.communicate(input=prompt, timeout=300)
            except subprocess.TimeoutExpired:
                proc.kill()
                out, _ = proc.communicate()
                store.update(task["id"], "failed", "超时（300秒）。\n" + out[-9000:])
                store.audit("codex_run_timeout", {"id":task["id"]})
                return
            status = "done" if proc.returncode == 0 else "failed"
            store.update(task["id"], status, out[-11000:])
            store.audit("codex_run_finished", {"id":task["id"],"exit_code":proc.returncode})
        except Exception as exc:
            store.update(task["id"], "failed", str(exc))
            store.audit("codex_run_error", {"id":task["id"],"error_type":type(exc).__name__})

    thread = threading.Thread(target=worker, name=f"codex-{task['id']}", daemon=True)
    thread.start()
