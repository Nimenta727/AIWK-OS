#!/usr/bin/env python3
"""Host-side model service: keeps llama-server (GPU) running on 127.0.0.1 and restarts it when it dies.

Runs on the HOST (Windows, Linux or macOS), standard library only. It only supervises the process and never opens a
port itself; the model listens on loopback and the guest reaches it solely through `aiws_model_channel.py host`.

  python aiws_host_model.py --llama C:\\llama\\llama-server.exe --model D:\\models\\qwen3-8b-q4_k_m.gguf --check
  python aiws_host_model.py --llama ... --model ...            # run, resident, auto-restart

`--check` runs `llama-server --help` and verifies EVERY flag this script passes still exists in your build, because
llama.cpp renames flags between releases. Do that once after each llama.cpp update. Nothing here was run against a real
GPU build in the repository's CI: the recommended values are a starting point to be measured with os/model/bench.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

# Starting point for a 12 GB card with a 7-8B Q4/Q5 model. Each entry is (flag, value or None). Measure, then adjust.
DEFAULTS = {
    "ctx": 16384,            # context window; KV memory grows with it
    "gpu_layers": "all",     # whole model on the GPU
    "flash_attn": "on",      # needs a CUDA build with flash attention
    "cache_k": "q8_0",       # quantised KV cache halves its memory with little quality loss; set "f16" to disable
    "cache_v": "q8_0",
    "parallel": 1,           # one slot: a single user; more slots split the context
    "cache_reuse": 256,      # reuse a shared prompt prefix between requests (the stable system prompt)
    "port": 8080,
}
HOST = "127.0.0.1"
SAFE_PATH = re.compile(r"^[^\x00-\x1f]{1,512}$")
SAFE_VALUE = re.compile(r"^[A-Za-z0-9_.:-]{1,24}$")


def build_argv(llama, model, cfg=None, alias="aiws-local"):
    c = {**DEFAULTS, **(cfg or {})}
    for key in ("gpu_layers", "flash_attn", "cache_k", "cache_v"):
        if not SAFE_VALUE.fullmatch(str(c[key])):
            raise ValueError("bad value for " + key)
    for key in ("ctx", "parallel", "cache_reuse", "port"):
        if isinstance(c[key], bool) or not isinstance(c[key], int) or not 0 <= c[key] <= 10 ** 7:
            raise ValueError("bad value for " + key)
    if not 1 <= c["port"] <= 65535 or not SAFE_PATH.fullmatch(llama) or not SAFE_PATH.fullmatch(model):
        raise ValueError("bad port or path")
    return [llama, "--model", model, "--alias", alias, "--host", HOST, "--port", str(c["port"]),
            "--ctx-size", str(c["ctx"]), "--n-gpu-layers", str(c["gpu_layers"]), "--flash-attn", str(c["flash_attn"]),
            "--cache-type-k", str(c["cache_k"]), "--cache-type-v", str(c["cache_v"]),
            "--parallel", str(c["parallel"]), "--cache-reuse", str(c["cache_reuse"])]


def flags_in(argv):
    return [a for a in argv if a.startswith("--")]


def missing_flags(help_text, argv):
    """Flags we pass that do not appear in `llama-server --help` (checked as whole tokens, so --cache-type-k is not satisfied by --cache-type-kv)."""
    present = set(re.findall(r"(?<![\w-])(--[a-z0-9][a-z0-9-]*)", help_text))
    return [f for f in flags_in(argv) if f not in present]


def check(llama, argv, run=subprocess.run):
    try:
        out = run([llama, "--help"], capture_output=True, text=True, timeout=30, shell=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, "cannot run %s: %s" % (llama, type(exc).__name__)
    return missing_flags((out.stdout or "") + (out.stderr or ""), argv), ""


class Backoff:
    """Restart delay 1,2,4,... up to 30 s; resets after the model stayed up for a minute, so a flapping model cannot spin."""
    def __init__(self):
        self.delay = 1.0
    def next(self, uptime):
        self.delay = 1.0 if uptime >= 60 else min(self.delay * 2, 30.0)
        return self.delay


def supervise(argv, popen=subprocess.Popen, sleep=time.sleep, clock=time.monotonic, log=print, max_restarts=None):
    backoff, restarts = Backoff(), 0
    while max_restarts is None or restarts <= max_restarts:
        started = clock()
        log("starting llama-server (restart #%d)" % restarts)
        try:
            code = popen(argv, stdin=subprocess.DEVNULL, shell=False).wait()
        except OSError as exc:
            log("cannot start: %s" % type(exc).__name__)
            code = -1
        delay = backoff.next(clock() - started)
        log("llama-server exited with %s; restarting in %.0fs" % (code, delay))
        restarts += 1
        sleep(delay)
    return restarts


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--llama", required=True, help="path to llama-server (CUDA build)")
    ap.add_argument("--model", required=True, help="path to the .gguf file")
    ap.add_argument("--config", help="JSON file overriding the defaults (ctx, gpu_layers, flash_attn, cache_k, cache_v, parallel, cache_reuse, port)")
    ap.add_argument("--check", action="store_true", help="verify the flags against your llama-server build and exit")
    a = ap.parse_args()
    cfg = {}
    if a.config:
        with open(a.config, encoding="utf-8") as fh:
            cfg = json.load(fh)
        if not isinstance(cfg, dict) or set(cfg) - set(DEFAULTS):
            sys.exit("config may only contain: " + ", ".join(DEFAULTS))
    if not os.path.isfile(a.model):
        sys.exit("model file not found")
    argv = build_argv(a.llama, a.model, cfg)
    if a.check:
        bad, why = check(a.llama, argv)
        if bad is None:
            sys.exit(why)
        print("all flags exist in this build" if not bad else "NOT SUPPORTED by this build: " + ", ".join(bad))
        sys.exit(1 if bad else 0)
    supervise(argv)


if __name__ == "__main__":
    main()
