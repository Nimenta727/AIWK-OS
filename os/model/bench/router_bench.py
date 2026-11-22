#!/usr/bin/env python3
"""Offline benchmark: can a small local model (a) route a request to a cost tier and (b) pick the relevant lines of a log?

  python router_bench.py --model PATH.gguf --label 2B [--threads 4] [--ctx 4096] [--out result.json] [--skip-logs]

Needs `llama-cpp-python` (pip) and a GGUF file. No network. Both tasks use grammar-constrained output, so a parse failure
is impossible and every miss is a real wrong answer.

Task A - routing. Input: one user sentence. Output: one of local | flash | pro.
  Gold labels are in ../ci/router_v1.jsonl. They are the author's judgement from the definitions in ROUTER_SYSTEM and have
  not been reviewed by anyone else: read the numbers as "agreement with those definitions", not as ground truth.
  Under-routing (gold pro answered flash/local, or gold flash answered local) is the costly error; over-routing only costs money.

Task B - log reading. Input: a log compressed by a deterministic step (repeat lines collapsed, rare lines kept first).
  Output: up to 4 line numbers. Logs are synthetic (seeded). Half of them are built so that a plain keyword grep misleads
  (harmless decoy errors first, root cause without an error keyword); that is by design and is reported separately.
  Two rule-only baselines are scored on the same logs, so the model's added value is visible.
"""
import argparse
import json
import os
import random
import re
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TIERS = ("local", "flash", "pro")
ROUTER_SYSTEM = (
    "You route a programmer's request to the cheapest model tier that can handle it. Answer with JSON only.\n"
    "- local: a single file, folder or system operation, or just reading, listing, searching or showing something. "
    "No reasoning about code is needed. Examples: list files, move or rename a file, show the end of a log, change a setting.\n"
    "- flash: ordinary coding work: write or change one function or script, fix an obvious bug, explain a file or a "
    "traceback, add a test, run a build and report. The answer is mostly in front of you.\n"
    "- pro: hard reasoning: design or architecture, changes across many files, bugs with an unknown cause (races, leaks, "
    "intermittent failures), security review, performance mysteries, migrations, proofs.\n"
    "Judge by the work needed, not by how long the sentence is. If unsure between two tiers, choose the higher one."
)
# Prompt B: same three tiers, but with an explicit decision order. Written after reading the failures of prompt A on router_v1,
# so it must only be judged on a set it was not tuned on (router_v2_heldout.jsonl).
ROUTER_SYSTEM_B = (
    "You route a programmer's request to the cheapest model tier that can handle it. Answer with JSON only. "
    "Decide in this order and stop at the first match:\n"
    "1. pro: it needs design or architecture, a many-file or whole-project change, a bug whose cause is unknown (race, deadlock, leak, "
    "intermittent or environment-specific failure), a security audit, a performance mystery, a migration, or a proof.\n"
    "2. flash: otherwise, if it writes, changes, fixes, converts, explains or tests code of any size (even renaming one variable or "
    "adding one method), or runs a build or tests and interprets the output.\n"
    "3. local: only if no code is written, changed or explained: it moves, copies, renames, lists, opens, searches, shows or reads "
    "files, folders or logs, or changes a system setting.\n"
    "The length of the sentence does not matter."
)
LOG_SYSTEM = (
    "You read a compressed log to find why a job failed. Each line is `L<number>` (the first line number where the message "
    "appeared), `x<count>` when it repeated, then the message. Answer with JSON only: the line numbers that most directly "
    "show the ROOT CAUSE, most relevant first, at most 4. The root cause is what went wrong first, not the last symptom, "
    "and not a harmless warning."
)


def chat(system, user):
    # Qwen ChatML with an empty thinking block = non-thinking mode, without depending on a template engine.
    return ("<|im_start|>system\n%s<|im_end|>\n<|im_start|>user\n%s<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n" % (system, user))


# ---------------------------------------------------------------- log generator (synthetic, seeded)
def _ts(i):
    return "2025-03-14 02:%02d:%02d" % ((i // 60) % 60, i % 60)


def _noise(rng, n, kinds):
    """`kinds` = (components, verbs). 10 x 8 = 80 distinct message templates, so compression cannot trivialise the task."""
    comps, verbs = kinds
    out = []
    for _ in range(n):
        out.append("%s %s %s %d" % (rng.choice(("INFO", "INFO", "DEBUG")), rng.choice(comps), rng.choice(verbs), rng.randint(1, 9999)))
    return out


APP = (("worker", "cache", "scheduler", "router", "pool", "session", "queue", "indexer", "metrics", "gateway"),
       ("accepted request", "refreshed entry", "rotated segment", "flushed buffer", "resolved route", "renewed lease", "reported latency ms", "compacted block"))
BUILD = (("cc", "ld", "ar", "codegen", "linker", "preproc", "depscan", "strip", "install", "pkgconfig"),
         ("compiled object", "scanned header", "resolved symbol", "wrote archive", "checked flags", "cached result", "generated stub", "linked module"))
TEST = (("auth", "billing", "search", "upload", "export", "profile", "cart", "notify", "report", "admin"),
        ("passed case", "passed fixture", "collected items", "skipped platform", "passed param", "setup ok", "teardown ok", "passed marker"))


def _build(rng, kind, hard):
    """Return (lines, gold_indexes) for one scenario. `hard` = grep for error words misleads."""
    gold = []
    lines = _noise(rng, 700, kind["noise"])
    if hard:
        for i, d in enumerate(kind["decoys"]):
            lines.insert(rng.randint(20, 300), d)               # harmless error-looking decoys early
    pos = rng.randint(330, 520)
    for g in kind["hard_gold" if hard else "easy_gold"]:
        lines.insert(pos, g)
        gold.append(pos)
        pos += 1
    lines.extend(_noise(rng, 90, kind["noise"]))
    lines.extend(kind["tail"])
    # decoys were inserted before pos, shifting it: recompute gold by content instead of position
    gold = [i for i, l in enumerate(lines) if l in (kind["hard_gold" if hard else "easy_gold"])]
    return ["%s %s" % (_ts(i), l) for i, l in enumerate(lines)], [g + 1 for g in gold]


KINDS = [
    {"noise": APP, "decoys": ["ERROR telemetry plugin 'otel' not installed, continuing", "ERROR could not read optional ~/.appconfig, using defaults",
                              "ERROR sentry dsn missing, error reporting disabled", "ERROR metrics exporter statsd unreachable, retrying later",
                              "ERROR license server check skipped (offline mode)", "ERROR font cache stale, rebuilding"],
     "hard_gold": ["WARN free space on /data is 0 bytes", "INFO writing checkpoint to /data/ckpt.bin"],
     "easy_gold": ["ERROR OSError: [Errno 28] No space left on device: '/data/ckpt.bin'"],
     "tail": ["INFO shutting down workers", "INFO exit code 1"]},
    {"noise": APP, "decoys": ["ERROR deprecated option --legacy ignored", "ERROR could not set process title", "ERROR color output disabled (not a tty)",
                              "ERROR locale en_US.UTF-8 missing, using C", "ERROR update check failed (timeout)", "ERROR crash reporter not configured"],
     "hard_gold": ["INFO connecting to db.internal:5432 as svc_batch", "INFO password authentication failed for user \"svc_batch\""],
     "easy_gold": ["FATAL password authentication failed for user \"svc_batch\""],
     "tail": ["INFO retries exhausted", "INFO job aborted"]},
    {"noise": BUILD, "decoys": ["warning: unused variable 'tmp' [-Wunused-variable]", "error: unknown warning option '-Wno-foo' (ignored)", "ERROR optional dependency libfoo not found, skipping feature",
                                "error: cached object is stale, rebuilding", "ERROR ccache not available", "error: git describe failed, using version 0.0.0"],
     "hard_gold": ["src/net/conn.c:211:5: implicit declaration of function 'epoll_pwait2'", "make[2]: *** [src/net/conn.o] Error 1"],
     "easy_gold": ["src/net/conn.c:211:5: fatal error: sys/epoll2.h: No such file or directory"],
     "tail": ["make: *** [all] Error 2"]},
    {"noise": TEST, "decoys": ["ERROR conftest: plugin 'cov' not found", "ERROR fixture 'tmp_cache' deprecated", "ERROR could not write .pytest_cache (read-only)",
                               "ERROR xdist disabled (single cpu)", "ERROR network marker: skipping online tests", "ERROR junit output path missing, ignored"],
     "hard_gold": ["tests/test_billing.py::test_refund_rounding assert Decimal('10.005') == Decimal('10.01')", "FAILED tests/test_billing.py::test_refund_rounding"],
     "easy_gold": ["FAILED tests/test_billing.py::test_refund_rounding - AssertionError: 10.005 != 10.01"],
     "tail": ["== 1 failed, 214 passed in 31.2s =="]},
    {"noise": APP, "decoys": ["ERROR optional gpu not found, using cpu", "ERROR hostname lookup slow (2s)", "ERROR clock skew 3ms ignored", "ERROR plugin dir missing, creating",
                              "ERROR tls session cache full, evicting", "ERROR log rotation lagging"],
     "hard_gold": ["WARN heap used 99% (7.9G/8.0G)", "INFO gc pause 4210 ms"],
     "easy_gold": ["ERROR java.lang.OutOfMemoryError: Java heap space"],
     "tail": ["INFO process killed by supervisor (exit 137)"]},
    {"noise": APP, "decoys": ["ERROR cannot open /etc/app/extra.d (optional)", "ERROR proxy env not set", "ERROR time sync warning ignored", "ERROR cache warmup failed, continuing",
                              "ERROR unused config key 'legacy_mode'", "ERROR could not chown pidfile, continuing"],
     "hard_gold": ["INFO loading model from /models/prod-v7.bin", "INFO model file size 0 bytes"],
     "easy_gold": ["ERROR RuntimeError: model file /models/prod-v7.bin is empty"],
     "tail": ["INFO startup aborted"]},
]


def make_logs(seed=7):
    rng = random.Random(seed)
    cases = []
    for k, kind in enumerate(KINDS):
        for hard in (False, True):
            lines, gold = _build(rng, kind, hard)
            cases.append({"id": "k%d-%s" % (k, "hard" if hard else "easy"), "hard": hard, "lines": lines, "gold": gold})
    return cases


def compress(lines, budget_chars=7000):
    """Deterministic: normalise numbers, merge identical templates, keep first line number and the repeat count."""
    groups = {}
    order = []
    for i, raw in enumerate(lines, 1):
        msg = re.sub(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d ", "", raw)
        key = re.sub(r"0x[0-9a-f]+|[0-9a-f]{8,}|\d+", "#", msg)
        if key in groups:
            groups[key][1] += 1
        else:
            groups[key] = [i, 1, msg]
            order.append(key)
    items = [groups[k] for k in order]
    text = lambda it: "L%d%s %s" % (it[0], (" x%d" % it[1]) if it[1] > 1 else "", it[2][:160])
    total = sum(len(text(it)) + 1 for it in items)
    if total > budget_chars:                                   # keep rare messages first, then restore line order
        keep, used = [], 0
        for it in sorted(items, key=lambda it: (it[1], it[0])):
            used += len(text(it)) + 1
            if used > budget_chars:
                break
            keep.append(it)
        items = sorted(keep, key=lambda it: it[0])
    return items, "\n".join(text(it) for it in items)


ERR = re.compile(r"error|fatal|exception|failed|denied|refused|killed|abort", re.I)


def baseline_grep(items, k=4):
    return [it[0] for it in items if ERR.search(it[2])][:k]


def baseline_tail(items, k=4):
    return [it[0] for it in items][-k:]


# ---------------------------------------------------------------- model runner
class Model:
    def __init__(self, path, threads, ctx):
        from llama_cpp import Llama, LlamaGrammar
        self.Grammar = LlamaGrammar
        t = time.monotonic()
        self.llm = Llama(model_path=path, n_ctx=ctx, n_threads=threads, n_batch=512, verbose=False)
        self.load_seconds = round(time.monotonic() - t, 1)
        self.ctx = ctx
        self.g_route = LlamaGrammar.from_string('root ::= "{\\"tier\\": \\"" ("local" | "flash" | "pro") "\\"}"')
        self.g_lines = LlamaGrammar.from_string('root ::= "{\\"lines\\": [" num ("," " "? num){0,3} "]}"\nnum ::= [0-9]{1,5}')

    def ask(self, system, user, grammar, max_tokens):
        t = time.monotonic()
        r = self.llm.create_completion(chat(system, user), grammar=grammar, max_tokens=max_tokens, temperature=0.0)
        dt = time.monotonic() - t
        u = r.get("usage", {})
        return r["choices"][0]["text"], dt, u.get("prompt_tokens"), u.get("completion_tokens")


def run_routing(m, cases, system=None):
    system = system or ROUTER_SYSTEM
    rows = []
    for c in cases:
        text, dt, pt, ct = m.ask(system, c["text"], m.g_route, 12)
        try:
            pred = json.loads(text)["tier"]
        except Exception:
            pred = "?"
        rows.append({"text": c["text"], "gold": c["tier"], "pred": pred, "sec": round(dt, 2), "promptTokens": pt})
    return rows


def score_routing(rows):
    n = len(rows)
    acc = sum(r["gold"] == r["pred"] for r in rows) / n
    rank = {t: i for i, t in enumerate(TIERS)}
    under = sum(rank.get(r["pred"], -1) < rank[r["gold"]] for r in rows) / n
    over = sum(rank.get(r["pred"], 9) > rank[r["gold"]] for r in rows) / n
    pro = [r for r in rows if r["gold"] == "pro"]
    conf = {g: {p: sum(1 for r in rows if r["gold"] == g and r["pred"] == p) for p in TIERS} for g in TIERS}
    zh = [r for r in rows if re.search(r"[\u4e00-\u9fff]", r["text"])]
    en = [r for r in rows if r not in zh]
    pct = lambda xs: round(sum(r["gold"] == r["pred"] for r in xs) / len(xs), 3) if xs else None
    return {"n": n, "accuracy": round(acc, 3), "underRoute": round(under, 3), "overRoute": round(over, 3),
            "proRecall": round(sum(r["pred"] == "pro" for r in pro) / len(pro), 3) if pro else None,
            "accuracyZh": pct(zh), "accuracyEn": pct(en), "confusion(gold->pred)": conf,
            "medianSec": round(statistics.median(r["sec"] for r in rows), 2), "maxSec": max(r["sec"] for r in rows)}


def run_logs(m, cases):
    rows = []
    for c in cases:
        items, text = compress(c["lines"])
        user = "Compressed log (%d lines -> %d entries):\n%s\n\nWhich lines show the root cause?" % (len(c["lines"]), len(items), text)
        out, dt, pt, ct = m.ask(LOG_SYSTEM, user, m.g_lines, 40)
        try:
            picked = [int(x) for x in json.loads(out)["lines"]][:4]
        except Exception:
            picked = []
        gold = set(c["gold"])
        rows.append({"id": c["id"], "hard": c["hard"], "picked": picked, "gold": sorted(gold), "hit": bool(gold & set(picked)),
                     "top1": bool(picked and picked[0] in gold), "sec": round(dt, 1), "promptTokens": pt,
                     "grepHit": bool(gold & set(baseline_grep(items))), "tailHit": bool(gold & set(baseline_tail(items))),
                     "goldInCompressed": bool(gold & {it[0] for it in items}), "rawLines": len(c["lines"]), "entries": len(items)})
    return rows


def score_logs(rows):
    def part(rs):
        if not rs:
            return None
        f = lambda key: round(sum(r[key] for r in rs) / len(rs), 3)
        return {"n": len(rs), "modelHit": f("hit"), "modelTop1": f("top1"), "grepHit": f("grepHit"), "tailHit": f("tailHit"),
                "goldSurvivesCompression": f("goldInCompressed"), "medianSec": round(statistics.median(r["sec"] for r in rs), 1)}
    return {"all": part(rows), "grepFriendly": part([r for r in rows if not r["hard"]]), "grepMisleading": part([r for r in rows if r["hard"]])}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model", required=True)
    ap.add_argument("--label", default="model")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--ctx", type=int, default=4096)
    ap.add_argument("--cases", default=os.path.join(HERE, "..", "ci", "router_v1.jsonl"))
    ap.add_argument("--prompt", choices=("A", "B"), default="A", help="router prompt variant")
    ap.add_argument("--out")
    ap.add_argument("--skip-logs", action="store_true")
    ap.add_argument("--skip-routing", action="store_true")
    a = ap.parse_args()
    m = Model(a.model, a.threads, a.ctx)
    result = {"label": a.label, "model": os.path.basename(a.model), "ctx": a.ctx, "threads": a.threads, "prompt": a.prompt, "cases": os.path.basename(a.cases), "loadSeconds": m.load_seconds}
    if not a.skip_routing:
        cases = [json.loads(l) for l in open(a.cases, encoding="utf-8") if l.strip()]
        rows = run_routing(m, cases, ROUTER_SYSTEM_B if a.prompt == "B" else ROUTER_SYSTEM)
        result["routing"] = score_routing(rows)
        result["routingMisses"] = [r for r in rows if r["gold"] != r["pred"]]
        print(json.dumps({"label": a.label, "routing": result["routing"]}, ensure_ascii=False, indent=1), flush=True)
    if not a.skip_logs:
        rows = run_logs(m, make_logs())
        result["logs"] = score_logs(rows)
        result["logRows"] = rows
        print(json.dumps({"label": a.label, "logs": result["logs"]}, ensure_ascii=False, indent=1), flush=True)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    sys.exit(main())
