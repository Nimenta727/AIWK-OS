"""Run the REAL workbench HTTP service on a throwaway demo workspace, for browser checks (workbench/e2e/ui-audit.cjs).

Not for production: the route and builder configs are fixed test values, and the guest-runtime guard is skipped
(make_server is what the tests use too). Prints "ready <port>" once it listens; Ctrl+C or SIGTERM stops it.
    python3 os/verify/fixtures/serve_workbench.py --ui workbench/dist [--port 0]
"""
import argparse
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "os/runtime"))


def demo_workspace(base):
    ws = base / "workspace"
    (ws / "src").mkdir(parents=True)
    (ws / "docs").mkdir()
    (ws / "README.md").write_text("# Demo project\n\nA small demo.\n")
    (ws / "src/main.py").write_text("def main():\n    print('hello')\n\nif __name__ == '__main__':\n    main()\n")
    (ws / "build.log").write_text("".join("[%04d] compiling unit %d\n" % (i, i) for i in range(300)) + "src/app.c:12: error: 'x' undeclared\n")
    (ws / "docs/notes.txt").write_text("notes\n")
    # the same fixtures the in-image GUI smoke test reads
    (ws / "AIWS-GUEST-SMOKE.txt").write_text("guest-only file manager acceptance fixture\n")
    (ws / "aiws-kernel.fragment").write_text("CONFIG_AIWS_DEMO=y\n")
    if shutil.which("git"):                       # so "Review changes" has something real to show
        env = dict(os.environ, GIT_AUTHOR_NAME="demo", GIT_AUTHOR_EMAIL="demo@example.invalid",
                   GIT_COMMITTER_NAME="demo", GIT_COMMITTER_EMAIL="demo@example.invalid")
        for argv in (["git", "init", "-q"], ["git", "add", "-A"], ["git", "commit", "-q", "-m", "demo"]):
            subprocess.run(argv, cwd=ws, env=env, check=False, capture_output=True)
        (ws / "README.md").write_text("# Demo project\n\nA small demo, edited.\n")
    return ws.resolve()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ui", required=True)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    base = pathlib.Path(tempfile.mkdtemp(prefix="aiws-ui-audit-"))
    ws = demo_workspace(base)
    (base / "home").mkdir()
    os.environ.update({"AIWS_WORKSPACE": str(ws), "XDG_STATE_HOME": str(base / "state"), "HOME": str(base / "home"),
                       "AIWS_SKILLS_DIR": str(base / "no-skills")})
    patch("aiws_workbench.load_config", lambda: {"externalEnabled": False, "providers": {},
                                                 "extraLocalKeywords": [], "extraExternalKeywords": []}).start()
    patch("aiws_workbench.load_builder_config", lambda: {"enabled": False, "envAllow": [], "isolation": {
        "mode": "none", "user": "x", "proxy": "http://127.0.0.1:3128"}}).start()
    from aiws_workbench import make_server
    server = make_server(ws, pathlib.Path(args.ui).resolve(), args.port)
    def stop(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)          # clean up the demo workspace on a normal kill too
    print("ready", server.server_port, flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    main()
