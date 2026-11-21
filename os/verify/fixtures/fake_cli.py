#!/usr/bin/env python3
"""SYNTHETIC stand-in for an official CLI, used only by tests. Not a real provider.

Usage: fake_cli.py SCENARIO [ARG]
It prints Claude-style stream-json lines and can misbehave: overspend, hang, spawn children, flood, etc.
"""
import json
import os
import subprocess
import sys
import time

def out(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()

def init():
    out({"type": "system", "subtype": "init", "session_id": "fake", "model": "fake-model"})

def assistant(i, usage=True, tool=None, text="hello"):
    content = [{"type": "text", "text": text}]
    if tool:
        content.append({"type": "tool_use", "id": "tu%d" % i, "name": tool[0], "input": tool[1]})
    msg = {"id": "m%d" % i, "content": content}
    if usage:
        i_, o_ = (1000, 500) if usage is True else usage
        msg["usage"] = {"input_tokens": i_, "output_tokens": o_}
    out({"type": "assistant", "message": msg})

def result(ok=True, total=(2000, 1000)):
    out({"type": "result", "subtype": "success" if ok else "error_during_execution", "is_error": not ok,
         "usage": {"input_tokens": total[0], "output_tokens": total[1]}, "num_turns": 2})

scenario = sys.argv[1] if len(sys.argv) > 1 else "ok"
arg = sys.argv[2] if len(sys.argv) > 2 else None
init()
if scenario == "ok":
    assistant(1, usage=(100, 20)); time.sleep(0.05); assistant(2, usage=(150, 40)); result(total=(250, 60))   # consistent with the total
elif scenario == "overbudget":
    for i in range(1, 400):
        assistant(i); time.sleep(0.03)
    result()
elif scenario == "hang":
    time.sleep(120)
elif scenario == "unknown":
    for i in range(1, 12):
        assistant(i, usage=False); time.sleep(0.03)
    result(total=(0, 0))
elif scenario == "turns":
    for i in range(1, 60):
        out({"type": "assistant", "message": {"id": "t%d" % i, "content": [{"type": "text", "text": "x"}], "usage": {"input_tokens": 1, "output_tokens": 1}}})
        time.sleep(0.02)
    result(total=(60, 60))
elif scenario == "tool":                  # ARG = "Tool|detail": announces a tool, waits, then finishes
    name, _, detail = (arg or "Bash|echo hi").partition("|")
    key = "file_path" if name in ("Edit", "Read", "Write") else "command"
    assistant(1, usage=(100, 20), tool=(name, {key: detail}))
    time.sleep(0.6)
    out({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "tu1", "content": "done"}]}})
    result(total=(250, 60))
elif scenario == "child":                 # spawn a grandchild and record its pid
    child = subprocess.Popen(["sleep", "120"])
    open(arg, "w").write(str(child.pid))
    time.sleep(120)
elif scenario == "env":
    sys.stdin.read()
    open(arg, "w").write(json.dumps({"cwd": os.getcwd(), "env": sorted(os.environ), "stdin_eof": True}))
    result(total=(10, 5))
elif scenario == "flood":
    for i in range(20000):
        sys.stdout.write("garbage %d\n" % i)
    sys.stdout.flush(); result(total=(10, 5))
elif scenario == "bigline":
    sys.stdout.write("x" * (2 * 1024 * 1024) + "\n"); sys.stdout.flush(); result(total=(10, 5))
elif scenario == "exit3":
    sys.stderr.write("fatal: SECRET_TOKEN=abc123xyz something broke\n"); sys.stderr.flush()
    sys.exit(3)
else:
    sys.exit(9)
