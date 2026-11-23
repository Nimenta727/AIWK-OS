"""Tier router: which cost tier should handle a request. It decides; it never runs anything and never calls the cloud.

  local  the machine itself (files, logs, settings, reading). No cloud tokens at all.
  flash  the cheap cloud model, thinking off: ordinary coding work.
  pro    the strong cloud model, thinking on: design, hard bugs, security, migrations.

Why a router at all, and why at the START of a task and not on every turn: switching the model in the middle of a conversation throws
away the provider's prompt cache (the whole history is billed again) and, for DeepSeek with tools, a reasoning trace that belongs to
the other model. So the choice is made once per task, and again only for a sub-agent, which has its own context anyway.

How it decides (2026-11-22 benchmark: docs/routine/2026-11-22_1032-...)
  1. Rules look for words that name something sensitive (network, root, secrets, writes ...). They only ADVISE: the decision lists them so the
     person sees "this will need approval", and the tier is NOT changed. A hard "stay local" rule was tried and measured: 10 of 10 ordinary
     programmer requests ("write a script that downloads a file with curl", "fix the ssh config parser", "explain chmod 755") hit a
     forbidden category, so it would have kept normal coding work off the cloud. The router is not the safety boundary; approvals,
     mandates and path confinement are.
  2. The local 9B model picks a tier from the prompt below. Its prompt has an explicit DECISION ORDER, because with plain
     definitions both 2B and 9B sent code-editing requests to `local` (flash: 4/30 right). With the order: 9B 96.7%, 2B 90% on a set
     that was not used to write it.
  3. Rules can only RAISE the tier (floors). Under-routing is the costly mistake (a hard task sent to a cheap tier fails quietly), while
     over-routing only costs money. A floor needs a clear marker: code in the message, a stack trace, "deadlock", "架构" ...
  4. Everything is explained to the user in both languages and can be overridden with one click. Overrides are counted: that is the
     honest measure of whether this router is any good.
If the model is not available the answer is `flash` (or higher if a floor says so) and it says so: no information is not a reason for `pro`.
"""
import json
import os
import re
import threading
from pathlib import Path

import aiws_llm
from aiws_deepseek import MODELS
from aiws_model_router import forbidden_categories

TIERS = ("local", "flash", "pro")
RANK = {t: i for i, t in enumerate(TIERS)}
SCHEMA = {"type": "object", "properties": {"tier": {"enum": list(TIERS)}}, "required": ["tier"], "additionalProperties": False}
MAX_TEXT = 1000

# Identical to ROUTER_SYSTEM_B of os/model/bench/router_bench.py (a test pins that, so the benchmark measures what ships).
PROMPT = (
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

# Floors: a clear marker raises the tier, never lowers it. Bounded patterns only (no nested repetition) on a 1000-character text.
FLOORS = (
    ("code-block", r"```", "flash"),
    ("stack-trace", r"traceback \(most recent|\bexception in thread\b|\bat \w+\.\w+\(.{0,40}\.(java|kt|py|js|ts|cs):\d+\)|segmentation fault|panicked at", "flash"),
    ("code-task", r"\b(fix|implement|refactor|debug|rewrite|optimi[sz]e|write)\b.{0,40}\b(function|method|class|test|tests|endpoint|script|module|query|regex|bug|code)\b", "flash"),
    ("code-task-zh", r"(修复|实现|重构|调试|优化|重写|编写|写一个|帮我写).{0,12}(函数|方法|类|测试|接口|脚本|模块|查询|正则|代码|程序|bug)", "flash"),
    ("code-error-zh", r"(崩溃|报错|抛出|异常).{0,12}(判断|处理|加个|加上|修)|(加|补).{0,6}(判断|校验|错误处理)", "flash"),
    ("hard-bug", r"\b(deadlock|race condition|memory leak|data race|heisenbug|intermittent(ly)?|flaky|only (on|in) (ci|prod|production))\b|\boccasionally\b.{0,40}\b(hang|freeze|crash|disagree)|\bwhy\b.{0,60}\b(only|sometimes|occasionally)\b", "pro"),
    ("hard-bug-zh", r"死锁|竞态|内存泄漏|内存暴涨|偶发|间歇|偶尔(会)?(卡|崩|挂|出现)|只在.{0,6}(生产|线上|CI|ARM)|高峰期|脏读|根因|根本原因", "pro"),
    ("design", r"\b(architecture|architect|design (a|an|the|how)|migrat(e|ion)|threat model|rollout|rollback strategy)\b", "pro"),
    ("design-zh", r"架构|重新设计|设计.{0,12}(方案|系统|协议|模型|缓存)|迁移|分阶段|权限系统|灰度", "pro"),
    ("security", r"\b(vulnerab\w*|security (audit|review)|exploit\w*|side[- ]channel|takeover|injection)\b|漏洞|安全审计|侧信道|填充攻击|被盗用", "pro"),
)
_COMPILED = tuple((name, re.compile(rx, re.I), tier) for name, rx, tier in FLOORS)

WHY = {
    "advisory": {"zh": "请求里提到了：{cats}。这不影响选哪一档，但云端智能体做这类操作前会先向你申请批准。",
                 "en": "The request mentions: {cats}. This does not change the tier, but the cloud agent asks for your approval before doing such things."},
    "local": {"zh": "只是查看、列出、移动或读取文件和日志，不需要写代码：在本机完成，不花云端 token。",
              "en": "Only viewing, listing, moving or reading files and logs; no code needed: done on this machine, no cloud tokens."},
    "flash": {"zh": "普通的写代码/改代码/解释代码任务：用便宜的 flash，关闭思考。",
              "en": "Ordinary coding work (write, change, fix, explain): the cheap flash model, thinking off."},
    "pro": {"zh": "需要设计、深入排查或安全评估：用 v4-pro，开启思考。",
            "en": "Needs design, deep diagnosis or a security review: v4-pro with thinking on."},
    "raised": {"zh": "规则把档位从 {a} 提高到 {b}（原因：{why}）。判得偏低的代价比多花一点钱大，所以只升不降。",
               "en": "A rule raised the tier from {a} to {b} (because: {why}). Under-routing costs more than overspending, so rules only raise."},
    "fallback": {"zh": "本地模型当前不可用，按默认的 flash 处理（你可以改）。",
                 "en": "The local model is not available, so the default flash applies (you can change it)."},
}


def cloud_choice(tier):
    """What to select in the cloud agent for a tier (None for local)."""
    if tier == "flash":
        return {"provider": "deepseek", "model": MODELS[0], "thinking": False}
    if tier == "pro":
        return {"provider": "deepseek", "model": MODELS[-1], "thinking": True}
    return None


def floor_for(text, extra=()):
    """(highest tier demanded by a rule or None, [marker names]). `extra` are plugin hints: {"pattern", "tier", "plugin"}."""
    best, names = None, []
    for name, rx, tier in _COMPILED:
        if rx.search(text):
            names.append(name)
            best = tier if best is None or RANK[tier] > RANK[best] else best
    for hint in extra:
        try:
            if re.search(hint["pattern"], text, re.I):
                names.append("plugin:%s" % hint.get("plugin", "?"))
                best = hint["tier"] if best is None or RANK[hint["tier"]] > RANK[best] else best
        except (re.error, KeyError):
            continue
    return best, names


def _explain(final, model_tier, floor_names, source):
    why = dict(WHY[final])
    if source == "rules-fallback":
        why = {k: WHY["fallback"][k] + " " + why[k] for k in why}
    if model_tier is not None and final != model_tier:
        raised = WHY["raised"]
        why = {k: why[k] + " " + raised[k].format(a=model_tier, b=final, why=", ".join(floor_names)) for k in why}
    return why


def decide(text, llm=None, extra_floors=()):
    """The routing decision for one request. `llm` is an aiws_llm.LocalLLM (None = rules only)."""
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= MAX_TEXT:
        raise ValueError("The request must be 1-%d characters" % MAX_TEXT)
    text = text.strip()
    advisories = forbidden_categories(text)
    floor, markers = floor_for(text, extra_floors)
    model_tier, source, usage, timing = None, "model", None, None
    if llm is not None:
        try:
            obj, meta = llm.complete_json([{"role": "system", "content": PROMPT}, {"role": "user", "content": text}], SCHEMA, max_tokens=20, repairs=1)
            model_tier, usage, timing = obj["tier"], meta["usage"], meta["timing"]
        except aiws_llm.LLMError:
            model_tier = None
    if model_tier is None:
        source = "rules-fallback" if llm is not None else "rules"
        base = "flash"
    else:
        base = model_tier
    final = floor if floor is not None and RANK[floor] > RANK[base] else base
    why = _explain(final, model_tier, markers, source)
    if advisories:
        names = {"network": ("联网", "network access"), "shell_root": ("命令/提权", "commands or root rights"), "host": ("宿主机/主机", "the host machine"),
                 "download_control": ("下载控制", "download control"), "permanent_delete": ("永久删除", "permanent deletion"),
                 "write_content": ("写入内容", "writing content"), "bypass": ("绕过/审计", "bypassing or audit"),
                 "path_escape": ("系统路径/密钥", "system paths or keys"), "cloud_or_exfil": ("云端/上传", "cloud or uploads")}
        why = {lang: why[lang] + " " + WHY["advisory"][lang].format(cats=", ".join(names.get(c, (c, c))[0 if lang == "zh" else 1] for c in advisories)) for lang in why}
    return {"tier": final, "thinking": final == "pro", "cloud": cloud_choice(final), "source": source, "modelTier": model_tier, "floor": floor,
            "markers": markers, "advisories": advisories, "why": why, "usage": usage, "timing": timing}


class RouteStats:
    """Counters that answer the only question that matters: is the router any good? Persisted, bounded, no text of any request."""

    KEYS = ("decisions", "local", "flash", "pro", "raisedByRule", "fallback", "overrides", "localCompleted", "localRefused")

    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()

    def _read(self):
        try:
            if self.path.is_symlink() or not self.path.is_file() or self.path.stat().st_size > 8192:
                raise OSError
            doc = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            doc = {}
        if not isinstance(doc, dict):
            doc = {}
        out = {k: (doc.get(k) if isinstance(doc.get(k), int) and not isinstance(doc.get(k), bool) and 0 <= doc.get(k) < 10 ** 9 else 0) for k in self.KEYS}
        out["overrideMatrix"] = {k: v for k, v in (doc.get("overrideMatrix") or {}).items() if re.fullmatch(r"(local|flash|pro)>(local|flash|pro)", str(k)) and isinstance(v, int) and 0 <= v < 10 ** 9} if isinstance(doc.get("overrideMatrix"), dict) else {}
        return out

    def _write(self, doc):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = self.path.with_name(self.path.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, sort_keys=True)
        os.replace(tmp, self.path)

    def record(self, decision):
        with self.lock:
            s = self._read()
            s["decisions"] += 1
            s[decision["tier"]] += 1
            s["raisedByRule"] += 1 if decision["modelTier"] and decision["tier"] != decision["modelTier"] else 0
            s["fallback"] += 1 if decision["source"] == "rules-fallback" else 0
            self._write(s)

    def override(self, from_tier, to_tier):
        if from_tier not in TIERS or to_tier not in TIERS or from_tier == to_tier:
            raise ValueError("Invalid override")
        with self.lock:
            s = self._read()
            s["overrides"] += 1
            k = "%s>%s" % (from_tier, to_tier)
            s["overrideMatrix"][k] = s["overrideMatrix"].get(k, 0) + 1
            self._write(s)

    def completed_locally(self, outcome):
        with self.lock:
            s = self._read()
            if outcome in ("final", "proposed"):
                s["localCompleted"] += 1
            elif outcome == "refused":
                s["localRefused"] += 1
            self._write(s)

    def get(self):
        with self.lock:
            s = self._read()
        d = s["decisions"]
        s["overrideRate"] = round(s["overrides"] / d, 3) if d else None
        s["localShare"] = round(s["local"] / d, 3) if d else None
        return s
