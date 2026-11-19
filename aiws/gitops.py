"""User-approved Git worktree creation. No general-purpose shell endpoint."""

import os
import shutil
import subprocess
from pathlib import Path


def create_task_worktree(task: dict, store) -> Path:
    """Make a clean isolated checkout at workspace/worktrees/<task-id>.

    Only call after separate explicit user confirmation. A repository's Git filters
    and config may run local processes even when Git arguments contain no shell.
    """
    git = shutil.which("git")
    if not git:
        raise FileNotFoundError("Git 未安装或未加入 PATH")
    project = store.project_path(task["project"])
    if not (project / ".git").exists():
        raise ValueError("请先在项目目录初始化 Git")
    target = store.worktree_root / task["id"]
    if target.exists() or target.is_symlink():
        raise ValueError("该任务的工作区已存在")
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"

    def run(*args, timeout=15):
        result = subprocess.run([git, "-C", str(project), *args], stdin=subprocess.DEVNULL,
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                encoding="utf-8", errors="replace", timeout=timeout,
                                env=env, check=False)
        if result.returncode:
            raise ValueError(f"Git 操作失败：{result.stderr.strip()[:600]}")
        return result.stdout.strip()

    repo_root = Path(run("rev-parse", "--show-toplevel")).resolve()
    if repo_root != project.resolve():
        raise ValueError("仅允许在项目 Git 根目录创建任务工作区")
    if run("status", "--porcelain"):
        raise ValueError("项目存在未提交修改；请先提交或暂存处理，再创建隔离工作区")
    branch = "aiws/" + task["id"].lower()
    run("worktree", "add", "-b", branch, str(target), "HEAD", timeout=35)
    if target.is_symlink() or target.resolve().parent != store.worktree_root.resolve():
        raise ValueError("Git 工作区路径异常，请手动检查")
    store.audit("create_task_worktree", {"id": task["id"], "branch": branch})
    return target
