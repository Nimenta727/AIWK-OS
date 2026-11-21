"""Capability index: one searchable registry of everything the local model may use, plus skills and memory.

Why it exists: a small local model picks the right tool far less reliably when it is shown dozens of them
(RAG-MCP, arXiv 2505.03275: ~13.6% -> ~43% selection accuracy when only a retrieved subset is shown). So the model
never sees the whole catalogue: `select(query, k)` returns a handful, ranked by a deterministic lexical index
(BM25 over words and CJK bigrams). No embeddings, no network, no model call: the same query always gives the same answer.

Three sources feed one index:
  tool    functions of the tool plane / declarative external tools / launchable apps (names and descriptions only)
  skill   short Markdown procedures. Trusted ones ship read-only in the system image (hash pinned in the manifest);
          anything a user or the AI adds lands in quarantine and is NOT retrievable until a person approves it.
  memory  short facts and preferences, bounded and secret-screened, which the user can list and forget.

Nothing here executes anything. It only decides what to SHOW the model; execution stays behind the Broker and approvals.
"""
import hashlib
import json
import math
import os
import re
import time
from pathlib import Path

MAX_SKILL_BYTES = 8192
MAX_SKILLS = 200
MAX_MEMORY = 500
MAX_MEMORY_CHARS = 400
SECRET_RE = re.compile(r"(?i)(api[_-]?key|secret|passw(or)?d|token|bearer\s+[a-z0-9]|-----BEGIN|sk-[a-z0-9]{12,}|ghp_[a-z0-9]{12,})")
KINDS = ("tool", "skill", "memory")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


class CapabilityError(Exception):
    """Safe-to-show rejection."""


# ---------- tokenisation ----------
_WORD = re.compile(r"[a-z0-9]+")
_CJK = re.compile(r"[㐀-鿿]+")


def tokens(text):
    text = (text or "").lower()
    out = _WORD.findall(text)
    for run in _CJK.findall(text):
        out.extend(run[i:i + 2] for i in range(len(run) - 1)) if len(run) > 1 else out.append(run)
    return out


# ---------- index ----------
class Index:
    """Small in-memory BM25. Documents are dicts with id, kind, title, text. Rebuilt on change; sizes are bounded."""

    def __init__(self, docs=()):
        self.docs = {}
        self._tf, self._df, self._len = {}, {}, {}
        for d in docs:
            self.add(d)

    def add(self, doc):
        ident = doc["id"]
        self.docs[ident] = doc
        toks = tokens(doc.get("title", "")) * 2 + tokens(doc.get("text", "")) + tokens(" ".join(doc.get("keywords", ())))
        tf = {}
        for t in toks:
            tf[t] = tf.get(t, 0) + 1
        self._tf[ident], self._len[ident] = tf, max(len(toks), 1)
        self._df = {}
        for f in self._tf.values():
            for t in f:
                self._df[t] = self._df.get(t, 0) + 1

    def remove(self, ident):
        for m in (self.docs, self._tf, self._len):
            m.pop(ident, None)
        self._df = {}
        for f in self._tf.values():
            for t in f:
                self._df[t] = self._df.get(t, 0) + 1

    def search(self, query, k=6, kinds=None):
        q = tokens(query)
        if not q or not self.docs:
            return []
        n = len(self.docs)
        avg = sum(self._len.values()) / n
        scored = []
        for ident, tf in self._tf.items():
            doc = self.docs[ident]
            if kinds and doc["kind"] not in kinds:
                continue
            score = 0.0
            for t in set(q):
                f = tf.get(t, 0)
                if not f:
                    continue
                idf = math.log(1 + (n - self._df[t] + 0.5) / (self._df[t] + 0.5))
                score += idf * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * self._len[ident] / avg))
            if score > 0:
                scored.append((-score, ident))
        scored.sort()                                              # ties broken by id: deterministic
        return [{**{k2: self.docs[i][k2] for k2 in ("id", "kind", "title")}, "score": round(-s, 3)} for s, i in scored[:max(1, min(k, 20))]]


# ---------- skills ----------
def parse_skill(text):
    """`---` front matter with name/title/keywords/requires, then a Markdown body. Strict and small."""
    if len(text.encode("utf-8")) > MAX_SKILL_BYTES:
        raise CapabilityError("Skill is larger than " + str(MAX_SKILL_BYTES) + " bytes")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        raise CapabilityError("Skill needs a --- front matter block")
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    name = meta.get("name", "")
    if not NAME_RE.fullmatch(name):
        raise CapabilityError("Skill name must be lowercase letters, digits, . _ -")
    requires = [x.strip() for x in meta.get("requires", "").split(",") if x.strip()]
    if len(requires) > 12:
        raise CapabilityError("Too many required tools")
    return {"name": name, "title": meta.get("title", name)[:80],
            "keywords": [x.strip() for x in meta.get("keywords", "").split(",") if x.strip()][:20],
            "requires": requires, "body": m.group(2).strip()}


def load_skill_dir(directory, pinned=None):
    """Read *.md skills. `pinned` maps name -> sha256; a file whose hash differs (or is unlisted) is skipped and reported."""
    skills, problems = [], []
    d = Path(directory)
    if not d.is_dir():
        return skills, problems
    for path in sorted(d.glob("*.md"))[:MAX_SKILLS]:
        if path.is_symlink() or not path.is_file():
            problems.append((path.name, "not a regular file"))
            continue
        try:
            raw = path.read_bytes()
            if len(raw) > MAX_SKILL_BYTES:
                raise CapabilityError("too large")
            skill = parse_skill(raw.decode("utf-8"))
            digest = hashlib.sha256(raw).hexdigest()
            if pinned is not None and pinned.get(skill["name"]) != digest:
                raise CapabilityError("hash does not match the pinned manifest")
        except (OSError, UnicodeDecodeError, CapabilityError) as exc:
            problems.append((path.name, str(exc)[:80]))
            continue
        skills.append({**skill, "sha256": digest})
    return skills, problems


# ---------- memory ----------
class MemoryStore:
    """Bounded JSONL of short notes. Secret-looking text is refused, entries can be listed and forgotten by the user."""

    def __init__(self, path):
        self.path = Path(path)

    def _read(self):
        try:
            return [json.loads(x) for x in self.path.read_text(encoding="utf-8").splitlines() if x.strip()]
        except (OSError, ValueError):
            return []

    def _write(self, rows):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = self.path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        os.replace(tmp, self.path)

    def list(self):
        return self._read()

    def add(self, text, kind="fact"):
        if kind not in ("fact", "preference", "project"):
            raise CapabilityError("Unknown memory kind")
        text = " ".join((text or "").split())
        if not 1 <= len(text) <= MAX_MEMORY_CHARS:
            raise CapabilityError("Memory must be 1–" + str(MAX_MEMORY_CHARS) + " characters")
        if SECRET_RE.search(text):
            raise CapabilityError("That looks like a secret; secrets are never stored in memory")
        rows = self._read()
        if any(r["text"] == text for r in rows):
            return next(r for r in rows if r["text"] == text)
        if len(rows) >= MAX_MEMORY:
            raise CapabilityError("Memory is full; forget something first")
        row = {"id": "m" + hashlib.sha256((text + str(time.time())).encode()).hexdigest()[:10], "kind": kind,
               "text": text, "ts": int(time.time())}
        self._write(rows + [row])
        return row

    def forget(self, ident):
        rows = self._read()
        keep = [r for r in rows if r["id"] != ident]
        if len(keep) == len(rows):
            raise CapabilityError("No such memory")
        self._write(keep)
        return {"forgotten": ident}


# ---------- the registry that ties it together ----------
class Capabilities:
    def __init__(self, tool_docs, skill_dirs=(), pinned=None, memory=None):
        """tool_docs: iterable of (name, description) for tool-plane / external tools / apps."""
        self.tool_docs = list(tool_docs)
        self.skill_dirs = [(Path(p), pinned if trusted else None) for p, trusted in skill_dirs]
        self.memory = memory
        self.problems = []
        self.refresh()

    def refresh(self):
        index = Index()
        for name, desc in self.tool_docs:
            index.add({"id": "tool:" + name, "kind": "tool", "title": name, "text": desc, "keywords": []})
        self.problems = []
        for directory, pinned in self.skill_dirs:
            skills, bad = load_skill_dir(directory, pinned)
            self.problems += bad
            for s in skills:
                index.add({"id": "skill:" + s["name"], "kind": "skill", "title": s["title"], "text": s["body"][:600],
                           "keywords": s["keywords"] + [s["name"]], "requires": s["requires"]})
        if self.memory:
            for r in self.memory.list():
                index.add({"id": "memory:" + r["id"], "kind": "memory", "title": r["kind"], "text": r["text"], "keywords": []})
        self.index = index

    def select(self, query, k=6, kinds=None):
        if kinds and not set(kinds) <= set(KINDS):
            raise CapabilityError("Unknown kind")
        hits = self.index.search(query, k, kinds)
        # A skill drags in the tools it declares, so the model gets a procedure AND the means to follow it, nothing more.
        extra = []
        for h in hits:
            for need in self.index.docs[h["id"]].get("requires", ()):
                tid = "tool:" + need
                if tid in self.index.docs and all(tid != x["id"] for x in hits + extra):
                    extra.append({"id": tid, "kind": "tool", "title": need, "score": 0.0})
        return (hits + extra)[:max(1, min(k + 4, 24))]

    def counts(self):
        out = {k: 0 for k in KINDS}
        for d in self.index.docs.values():
            out[d["kind"]] += 1
        return {**out, "problems": len(self.problems)}
