"""Observatory read model: builds the one-screen summary from existing facts. Pure functions.

No model call, no network, no process. Everything shown is derived from the task DAG, its audit chain,
the event store and local status; numbers the providers did not report stay unknown (None).
"""
TOKEN_KEYS = ("in", "out", "cacheRead", "cacheWrite")

def token_totals(sessions):
    """Sum only what was REPORTED. Sessions without numbers are counted, never guessed."""
    total = {k: None for k in TOKEN_KEYS}
    known = unknown = unverified = 0
    for s in sessions:
        t = s["tokens"]
        if t["basis"] == "none":
            unknown += 1
            continue
        known += 1
        unverified += 0 if t["verified"] else 1
        for key in TOKEN_KEYS:
            if t[key] is not None:
                total[key] = (total[key] or 0) + t[key]
    return {**total, "knownSessions": known, "unknownSessions": unknown, "unverifiedSessions": unverified}

def token_by_agent(sessions):
    groups = {}
    for s in sessions:
        groups.setdefault(s["agent"], []).append(s)
    return {agent: token_totals(items) for agent, items in sorted(groups.items())}

def verdict(audit, overview, sessions, now_text=None):
    """Red/yellow/green plus up to three plain sentences (bilingual). Rules only, no model."""
    stages = overview["stages"]
    failed = stages.get("failed", 0)
    waiting = len(overview["needsApproval"])
    errored = sum(1 for s in sessions if s["status"] == "error")
    unrecognized = sum(s["unrecognizedEvents"] for s in sessions)
    totals = token_totals(sessions)
    sentences = []
    if not audit.get("valid", False):
        level = "red"
        sentences.append({"zh": "审计链校验失败：已阻止新的调度，请先检查审计记录。",
                          "en": "Audit chain verification failed: scheduling is blocked; inspect the audit records first."})
    else:
        level = "green"
        sentences.append({"zh": "审计链完整，共 %d 条记录，没有被篡改的迹象。" % audit.get("events", 0),
                          "en": "The audit chain is intact (%d records) with no sign of tampering." % audit.get("events", 0)})
    done = stages.get("completed", 0)
    sentences.append({"zh": "共 %d 个任务：%d 个阶段完成，%d 个失败，%d 个等待你批准。" % (overview["tasks"], done, failed, waiting),
                      "en": "%d tasks: %d stages completed, %d failed, %d waiting for your approval." % (overview["tasks"], done, failed, waiting)})
    quality = []
    if totals["unknownSessions"] or totals["unverifiedSessions"]:
        quality.append(("有 %d 个会话的用量来源未知，%d 个未验证语义；这些数字不会被估算。" % (totals["unknownSessions"], totals["unverifiedSessions"]),
                        "%d sessions have unknown usage and %d unverified semantics; those numbers are never estimated." % (totals["unknownSessions"], totals["unverifiedSessions"])))
    if unrecognized:
        quality.append(("有 %d 个无法识别的事件，需要核对适配器。" % unrecognized,
                        "%d events were not recognised; check the adapter." % unrecognized))
    if quality:
        sentences.append({"zh": quality[0][0], "en": quality[0][1]})
    if level == "green" and (failed or waiting or errored or quality):
        level = "yellow"
    return {"level": level, "sentences": sentences[:3]}

def build_summary(*, sessions, overview, audit, model, router, demo, recent_events, builder=None, budget=None):
    return {
        "demo": demo,
        "status": {"localModel": {"configured": model["configured"], "online": model["online"], "weightsPresent": model["weightsPresent"]},
                   "builder": builder or {"state": "not-configured"},
                   "router": {"externalEnabled": router["externalEnabled"]}},
        "tokens": {"total": token_totals(sessions), "byAgent": token_by_agent(sessions), "budget": budget},
        "tasks": overview,
        "sessions": sessions,
        "recent": recent_events,
        "verdict": verdict(audit, overview, sessions),
        "audit": {"valid": bool(audit.get("valid")), "events": audit.get("events", 0)},
    }
