#!/usr/bin/env python3
"""Reject mismatched real-model smoke arguments before CPU model loading.

This runs against the exact pinned llama-server binary compiled for Debian 13,
not a mock. It validates CLI availability, but NOT successful model inference.
"""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from inference_smoke import server_command

def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python3 check_llama_cli.py /path/to/llama-server")
    binary=Path(sys.argv[1]).resolve(strict=True)
    if not binary.is_file():
        raise SystemExit("Real server executable is unavailable")
    proc=subprocess.run([str(binary),"--help"],timeout=35,
                        stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                        text=True,errors="replace",check=False)
    if proc.returncode != 0:
        raise SystemExit("Pinned llama-server --help failed (exit "+str(proc.returncode)+")")
    options=proc.stdout
    argv=server_command(executable=str(binary))
    # Long --flag tokens only; value strings are validated by the smoke itself.
    flags=[arg for arg in argv[1:] if arg.startswith("--")]
    missing=[flag for flag in flags if flag not in options]
    if missing:
        raise SystemExit("Pinned llama-server does not advertise required flags: "+", ".join(missing))
    if "--no-mmap" in flags:
        raise SystemExit("Smoke must not use deprecated --no-mmap")
    print("AIWS_MODEL_CLI_COMPAT_PASS flags="+str(len(flags)),flush=True)

if __name__=="__main__":
    main()
