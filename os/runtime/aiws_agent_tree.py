"""Sub-agent tree from recorded events. Pure function: no I/O, no model, nothing estimated.

A node is one agent: the main agent ("root") or a sub-agent spawned by a Task/Agent tool call. Everything shown for a
node comes from events the provider actually reported: its parent, label, model (own, else inherited and marked as such),
the context references it used (files, searches, URLs, commands, prompt size), tool-call count, tokens and time.
Where the stream did not say something, the field stays None/"unknown" instead of being guessed.
"""
MAX_NODES = 500
MAX_CTX = 12
ROOT = "root"


def _new(ident, parent, inferred=False):
    return {"id": ident, "parent": parent, "label": None, "model": None, "modelInherited": False, "state": "running",
            "tools": 0, "ctx": [], "tokens": {"in": None, "out": None}, "startedTs": None, "endedTs": None,
            "durationMs": None, "inferred": inferred, "children": []}


def _add_tokens(node, t, scope):
    for key in ("in", "out"):
        v = t.get(key)
        if v is None:
            continue
        cur = node["tokens"][key]
        node["tokens"][key] = v if scope == "total" else (cur or 0) + v


def build(events):
    events = sorted(events or [], key=lambda e: (e.get("seq", 0), e.get("ts", 0)))
    nodes = {ROOT: _new(ROOT, None)}
    nodes[ROOT]["label"] = "main"
    dropped = 0
    ended = False
    for e in events:
        ts = e.get("ts")
        if e.get("kind") == "start" and isinstance(e.get("detail"), str):
            nodes[ROOT]["model"] = nodes[ROOT]["model"] or e["detail"]
            nodes[ROOT]["startedTs"] = nodes[ROOT]["startedTs"] or ts
        if e.get("kind") == "end":
            ended = True
            nodes[ROOT]["endedTs"] = ts
            nodes[ROOT]["state"] = "error" if e.get("status") == "error" else ("done" if e.get("status") == "ok" else "unknown")
        nid = e.get("node") or ROOT
        spawn = e.get("kind") == "tool" and e.get("parent") and e.get("node")
        if nid not in nodes:
            if len(nodes) >= MAX_NODES:
                dropped += 1
                continue
            nodes[nid] = _new(nid, e.get("parent") if spawn else ROOT, inferred=not spawn)
        n = nodes[nid]
        if spawn:
            n["inferred"] = False
            n["parent"] = e["parent"] if e["parent"] != nid else ROOT
            n["startedTs"] = n["startedTs"] or ts
        for key in ("label", "model"):
            if e.get(key):
                n[key] = e[key]
        if e.get("kind") == "tool" and e.get("tool") in ("Task", "Agent") and e.get("node") and not e.get("parent"):
            # the result of the spawning call: the child finished (this is the only "done" signal some streams give)
            if e.get("status") in ("ok", "error"):
                n["state"] = "done" if e["status"] == "ok" else "error"
                n["endedTs"] = ts
        elif e.get("kind") == "message" and e.get("node") and e.get("status") in ("ok", "error") and nid != ROOT:
            n["state"] = "done" if e["status"] == "ok" else "error"
            n["endedTs"] = ts
        if e.get("kind") == "tool" and e.get("status") == "pending" and not spawn:
            n["tools"] += 1
        for c in e.get("ctx") or []:
            if c not in n["ctx"] and len(n["ctx"]) < MAX_CTX:
                n["ctx"].append(c)
        if e.get("prog"):
            n["tools"] = max(n["tools"], e["prog"]["tools"])
            n["durationMs"] = e["prog"]["ms"]
        t = e.get("tokens")
        if t and t.get("source") == "reported":
            _add_tokens(n, t, t.get("scope", "delta"))
    # wire the tree; an unknown or self/cyclic parent falls back to root so every node is reachable
    for n in nodes.values():
        if n["id"] == ROOT:
            continue
        p = n["parent"]
        if p not in nodes or p == n["id"]:
            p = n["parent"] = ROOT
        seen, cur = {n["id"]}, p
        while cur and cur != ROOT:
            if cur in seen:
                n["parent"] = ROOT
                break
            seen.add(cur)
            cur = nodes[cur]["parent"]
        nodes[n["parent"]]["children"].append(n["id"])
    for n in nodes.values():
        if n["durationMs"] is None and n["startedTs"] and n["endedTs"]:
            n["durationMs"] = int((n["endedTs"] - n["startedTs"]) * 1000)
        if n["state"] == "running" and ended and n["id"] != ROOT:
            n["state"] = "unknown"                       # the whole stream ended without this child reporting a result
    # model inheritance, parents before children
    def inherit(nid, model):
        n = nodes[nid]
        if not n["model"] and model:
            n["model"], n["modelInherited"] = model, True
        for c in n["children"]:
            inherit(c, n["model"])
    inherit(ROOT, None)
    ordered = []
    def walk(nid, depth):
        nodes[nid]["depth"] = depth
        ordered.append(nodes[nid])
        for c in nodes[nid]["children"]:
            walk(c, depth + 1)
    walk(ROOT, 0)
    return {"nodes": ordered, "count": len(ordered), "droppedNodes": dropped, "ended": ended}
