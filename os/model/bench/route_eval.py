#!/usr/bin/env python3
"""Evaluate the SHIPPED router (aiws_route.decide: model + rule floors) against a running OpenAI-compatible server.

  python route_eval.py --url http://127.0.0.1:18090 --cases ../ci/router_v3_fresh.jsonl [--out result.json]

Needs only a loopback server (llama-server, llama-cpp-python's server ...). Reports for the SAME run:
  model only      what the model said before any rule looked at it
  router          the final tier after the rule floors (this is what the user gets)
  floors          how often a rule raised the tier, and how often that raise was WRONG (above the label)
Labels are the author's. A set is only evidence of generalisation if it was written before the prompt and the rules were
tuned; the file names say which is which (router_v3_fresh was fixed before any model result was seen).
"""
import argparse
import json
import os
import re
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "runtime"))
import aiws_llm  # noqa: E402
import aiws_route as R  # noqa: E402


def score(rows, key):
    n = len(rows)
    rank = R.RANK
    acc = sum(r["gold"] == r[key] for r in rows) / n
    under = sum(rank[r[key]] < rank[r["gold"]] for r in rows) / n
    over = sum(rank[r[key]] > rank[r["gold"]] for r in rows) / n
    zh = [r for r in rows if re.search(r"[一-鿿]", r["text"])]
    en = [r for r in rows if r not in zh]
    pct = lambda xs: round(sum(r["gold"] == r[key] for r in xs) / len(xs), 3) if xs else None
    conf = {g: {p: sum(1 for r in rows if r["gold"] == g and r[key] == p) for p in R.TIERS} for g in R.TIERS}
    return {"accuracy": round(acc, 3), "underRoute": round(under, 3), "overRoute": round(over, 3), "accuracyZh": pct(zh), "accuracyEn": pct(en), "confusion": conf}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", default="http://127.0.0.1:18080")
    ap.add_argument("--cases", required=True)
    ap.add_argument("--out")
    ap.add_argument("--timeout", type=int, default=300)
    a = ap.parse_args()
    llm = aiws_llm.LocalLLM(a.url, timeout=a.timeout)
    cases = [json.loads(l) for l in open(a.cases, encoding="utf-8") if l.strip()]
    rows = []
    for c in cases:
        t = time.monotonic()
        d = R.decide(c["text"], llm)
        rows.append({"text": c["text"], "gold": c["tier"], "model": d["modelTier"] or "none", "router": d["tier"], "source": d["source"], "markers": d["markers"],
                     "advisories": d["advisories"], "sec": round(time.monotonic() - t, 2)})
        print("%-5s model=%-5s router=%-5s %s" % (c["tier"], rows[-1]["model"], rows[-1]["router"], c["text"][:60]), flush=True)
    usable = [dict(r, model=r["model"] if r["model"] != "none" else "flash") for r in rows]
    raised = [r for r in rows if r["model"] != "none" and r["router"] != r["model"]]
    result = {"cases": os.path.basename(a.cases), "n": len(rows), "modelOnly": score(usable, "model"), "router": score(rows, "router"),
              "floorRaises": len(raised), "floorRaisesWrong": sum(R.RANK[r["router"]] > R.RANK[r["gold"]] for r in raised),
              "floorRaisesRight": sum(R.RANK[r["router"]] <= R.RANK[r["gold"]] and R.RANK[r["model"]] < R.RANK[r["router"]] for r in raised),
              "modelUnavailable": sum(r["source"] == "rules-fallback" for r in rows), "withAdvisories": sum(bool(r["advisories"]) for r in rows),
              "medianSec": round(statistics.median(r["sec"] for r in rows), 2)}
    print(json.dumps(result, ensure_ascii=False, indent=1))
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump({**result, "rows": rows}, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    sys.exit(main())
