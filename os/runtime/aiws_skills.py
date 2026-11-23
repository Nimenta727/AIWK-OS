"""Skills for the local agent: Markdown procedures that are shown by NAME and loaded only when needed.

Format: the open Agent Skills layout (agentskills.io): `<skill-name>/SKILL.md` with a YAML front matter (name, description,
license, compatibility, metadata, allowed-tools) and a Markdown body. The older single-file AIWS skills
(`name.md` with name/title/keywords/requires) are read too, so the first-party skills keep working.

Progressive disclosure (the point of the format, and the only way a small model with a short context can have many skills):
  level 1  name + one-line description of EVERY skill sits in the system prompt (about 25 tokens each)
  level 2  the body is loaded into the conversation only when the model asks for that skill (`{"type":"skill"}`)
  level 3  `scripts/`, `references/`, `assets/` are NOT used: nothing a skill ships is ever executed, and extra files are listed
           as ignored so nobody believes they run.

A skill can never give the model more power. `allowed-tools` names the tools the skill needs: while the skill is in use they are SHOWN
to the model, but only if the agent has them at all (read tools can run, write tools can only be proposed); a skill cannot add
a tool the agent does not own. Only names that are real AIWS tools count (Claude-style names such as `Bash(git:*)` are reported as
ignored). A skill body is instructions for a model that is already confined: reads only, writes become proposals a person approves,
paths are workspace-relative. Standard library only; no network.
"""
import hashlib
import re
from pathlib import Path

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
LEGACY_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
TOOL_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[A-Za-z0-9_]+)+$")
MAX_FRONT = 8 * 1024
MAX_FILE = 64 * 1024
MAX_BODY = 6 * 1024              # about 1500 tokens: a skill larger than this is listed but refused to load into a small model
MAX_DESCRIPTION = 1024
MAX_SKILLS = 200


class SkillError(ValueError):
    """Safe to show to the user."""


def _scalar(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def parse_frontmatter(text):
    """(fields, body). A deliberately small YAML subset: `key: value`, quoted values, `|` and `>` block scalars, and one
    level of nested `key:` + indented `k: v` lines (for `metadata`). Anything fancier is a SkillError, never guessed at."""
    if not text.startswith("---"):
        raise SkillError("A skill needs a --- front matter block")
    m = re.match(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)(.*)\Z", text, re.S)
    if not m:
        raise SkillError("The front matter block is not closed with ---")
    raw, body = m.group(1), m.group(2)
    if len(raw.encode("utf-8")) > MAX_FRONT:
        raise SkillError("Front matter is too large")
    fields, lines, i = {}, raw.splitlines(), 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[0] in " \t":
            raise SkillError("Unexpected indentation in the front matter")
        key, sep, rest = line.partition(":")
        key = key.strip()
        if not sep or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,40}", key):
            raise SkillError("Cannot read front matter line: " + line[:40])
        rest = rest.strip()
        block = []
        while i < len(lines) and (lines[i][:1] in (" ", "\t") or not lines[i].strip()):
            block.append(lines[i])
            i += 1
        while block and not block[-1].strip():
            block.pop()
        if rest in ("|", ">", "|-", ">-"):
            parts = [b.strip() for b in block]
            fields[key] = ("\n" if rest.startswith("|") else " ").join(parts).strip()
        elif rest == "" and block:
            nested = {}
            for b in block:
                if not b.strip():
                    continue
                k, s2, v = b.strip().partition(":")
                if not s2:
                    raise SkillError("Nested front matter values must be key: value")
                nested[k.strip()] = _scalar(v)
            fields[key] = nested
        elif block:
            raise SkillError("Unexpected indented line after " + key)
        else:
            fields[key] = _scalar(rest)
    return fields, body.strip()


def map_allowed_tools(value, known):
    """Space-separated `allowed-tools` -> (honored, ignored). Only exact AIWS tool names count."""
    honored, ignored = [], []
    for token in str(value or "").split():
        (honored if TOOL_RE.match(token) and token in known else ignored).append(token)
    return sorted(set(honored)), sorted(set(ignored))


def parse_skill_md(text, dirname=None, known_tools=()):
    """One `SKILL.md`. Returns a skill dict; raises SkillError for anything unacceptable."""
    if len(text.encode("utf-8")) > MAX_FILE:
        raise SkillError("SKILL.md is larger than %d KiB" % (MAX_FILE // 1024))
    fields, body = parse_frontmatter(text)
    name, desc = fields.get("name"), fields.get("description")
    if not isinstance(name, str) or len(name) > 64 or not NAME_RE.match(name):
        raise SkillError("name must be 1-64 lowercase letters, digits and single hyphens")
    if not isinstance(desc, str) or not 1 <= len(desc) <= MAX_DESCRIPTION:
        raise SkillError("description is required and must be 1-%d characters" % MAX_DESCRIPTION)
    warnings = []
    if dirname is not None and dirname != name:
        warnings.append("name '%s' differs from its folder '%s'" % (name, dirname))
    honored, ignored = map_allowed_tools(fields.get("allowed-tools"), set(known_tools))
    return {"name": name, "description": " ".join(desc.split()), "body": body, "allowedTools": honored, "ignoredTools": ignored,
            "license": fields.get("license") if isinstance(fields.get("license"), str) else None, "format": "agentskills",
            "keywords": [], "requires": [], "tooLarge": len(body.encode("utf-8")) > MAX_BODY, "warnings": warnings}


def parse_legacy(text):
    """The first-party single-file form (name, title, keywords, requires) mapped onto the same shape."""
    import aiws_capabilities as caps
    try:
        s = caps.parse_skill(text)
    except caps.CapabilityError as exc:
        raise SkillError(str(exc))
    return {"name": s["name"], "description": s["title"], "body": s["body"], "allowedTools": [], "ignoredTools": [], "license": None,
            "format": "legacy", "keywords": s["keywords"], "requires": s["requires"],
            "tooLarge": len(s["body"].encode("utf-8")) > MAX_BODY, "warnings": []}


def load_dir_skills(directory, known_tools=(), pinned=None):
    """Read `<dir>/<skill>/SKILL.md` folders and `<dir>/*.md` legacy files. Returns (skills, problems, ignored_files).
    `pinned` (name -> sha256) is for the read-only system directory: a file whose hash is not listed is skipped, not trusted."""
    skills, problems, ignored = [], [], []
    d = Path(directory)
    if not d.is_dir() or d.is_symlink():
        return skills, problems, ignored
    for entry in sorted(d.iterdir(), key=lambda p: p.name)[:MAX_SKILLS]:
        try:
            if entry.is_symlink():
                problems.append((entry.name, "symlinks are not followed"))
                continue
            if entry.is_dir():
                md = entry / "SKILL.md"
                for extra in sorted(entry.iterdir()):
                    if extra.name != "SKILL.md":
                        ignored.append((entry.name + "/" + extra.name, "not used: a skill's scripts, references and assets are never executed or loaded"))
                if not md.is_file() or md.is_symlink():
                    problems.append((entry.name, "no SKILL.md"))
                    continue
                raw = md.read_bytes()
                skill = parse_skill_md(raw.decode("utf-8"), entry.name, known_tools)
            elif entry.suffix == ".md" and entry.is_file() and entry.name != "README.md":
                raw = entry.read_bytes()
                if len(raw) > MAX_FILE:
                    raise SkillError("too large")
                skill = parse_legacy(raw.decode("utf-8"))
            else:
                continue
            digest = hashlib.sha256(raw).hexdigest()
            if pinned is not None and pinned.get(skill["name"]) != digest:
                raise SkillError("hash does not match the pinned manifest")
            skill["sha256"] = digest
            skills.append(skill)
        except (OSError, UnicodeDecodeError, SkillError) as exc:
            problems.append((entry.name, str(exc)[:100]))
    return skills, problems, ignored


class SkillBook:
    """All skills the local agent may use, by id. Sources: the pinned system directory and the ENABLED plugins.
    An id is `name` for system skills and `plugin:name` for plugin skills (so nothing can shadow a system skill)."""

    def __init__(self, system_dir=None, pinned=None, plugins=None, known_tools=()):
        self.system_dir, self.pinned, self.plugins, self.known = system_dir, pinned, plugins, set(known_tools)
        self.refresh()

    def refresh(self):
        self.skills, self.problems = {}, []
        if self.system_dir is not None:
            found, bad, _ = load_dir_skills(self.system_dir, self.known, self.pinned if self.pinned is not None else {})
            self.problems += [("system/" + n, why) for n, why in bad]
            for s in found:
                self.skills[s["name"]] = {**s, "id": s["name"], "source": "system", "trusted": True}
        if self.plugins is not None:
            for s in self.plugins.active_skills(self.known):
                if s["id"] in self.skills:
                    self.problems.append((s["id"], "id already taken"))
                    continue
                self.skills[s["id"]] = s

    def catalog(self):
        """Level 1: [(id, description, source)] sorted by id: byte-identical until a skill is added or removed."""
        return [(k, self.skills[k]["description"], self.skills[k]["source"]) for k in sorted(self.skills)]

    def get(self, skill_id):
        return self.skills.get(skill_id)

    def load_text(self, skill_id):
        """Level 2: the text that goes into the conversation. Refuses a body too large for a small model."""
        s = self.get(skill_id)
        if s is None:
            raise SkillError("No such skill: " + str(skill_id)[:60])
        if s["tooLarge"]:
            raise SkillError("Skill '%s' is larger than %d KiB, too big for the local model" % (skill_id, MAX_BODY // 1024))
        return s["body"]
