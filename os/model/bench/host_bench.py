#!/usr/bin/env python3
"""Measure a loopback llama-server (or the guest model channel): latency, generation speed, and the prompt-prefix cache.

  python host_bench.py --url http://127.0.0.1:8080 [--runs 5] [--json out.json]

Reports, for the same stable system prompt: first-request time (cold: model or prefix not yet processed), warm
time, time with a changed user turn (prefix reused), tokens/s from the server's own `usage` (never estimated; missing usage is
reported as null). Standard library only; run it on the machine that has the GPU. Loopback URLs only.
"""
import argparse
import json
import statistics
import sys
import time
import urllib.request
from urllib.parse import urlsplit

SYSTEM = "You are a file assistant. Answer with one short sentence. " * 20      # stable prefix, long enough to matter


def one(url, user, max_tokens=64, timeout=300):
    body = json.dumps({"model": "aiws-local", "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
                       "max_tokens": max_tokens, "temperature": 0, "cache_prompt": True}).encode()
    req = urllib.request.Request(url.rstrip("/") + "/v1/chat/completions", data=body, headers={"Content-Type": "application/json"}, method="POST")
    t = time.monotonic()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read())
    dt = time.monotonic() - t
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    out = usage.get("completion_tokens") if isinstance(usage.get("completion_tokens"), int) else None
    return {"seconds": round(dt, 3), "completionTokens": out, "promptTokens": usage.get("prompt_tokens") if isinstance(usage.get("prompt_tokens"), int) else None,
            "tokensPerSecond": round(out / dt, 1) if out and dt > 0 else None}


def summarise(rows):
    secs = [r["seconds"] for r in rows]
    tps = [r["tokensPerSecond"] for r in rows if r["tokensPerSecond"] is not None]
    return {"n": len(rows), "medianSeconds": round(statistics.median(secs), 3), "maxSeconds": max(secs),
            "medianTokensPerSecond": round(statistics.median(tps), 1) if tps else None}


def run(url, runs=5, call=one):
    first = call(url, "list the files")                                # cold
    warm = [call(url, "list the files") for _ in range(runs)]          # identical request
    varied = [call(url, "list the files in folder %d" % i) for i in range(runs)]   # same prefix, new user turn
    return {"cold": first, "warm": summarise(warm), "prefixReuse": summarise(varied),
            "note": "tokens/s comes from the server's usage numbers; null means the server did not report them"}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", default="http://127.0.0.1:8080"); ap.add_argument("--runs", type=int, default=5); ap.add_argument("--json")
    a = ap.parse_args()
    u = urlsplit(a.url)
    if u.scheme != "http" or u.hostname not in ("127.0.0.1", "localhost", "::1"):
        sys.exit("loopback http URLs only")
    result = run(a.url, max(1, min(a.runs, 50)))
    print(json.dumps(result, indent=1))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=1)


if __name__ == "__main__":
    main()
