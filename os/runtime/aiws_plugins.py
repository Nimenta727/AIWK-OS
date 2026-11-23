"""Plugins for the local agent: a folder that bundles skills, slash commands and guards. It carries TEXT, never code.

Layout (the Claude Code plugin convention, so existing plugin authors recognise it):
    <plugin>/.claude-plugin/plugin.json     optional; only "name" is required   (or <plugin>/plugin.json)
    <plugin>/skills/<skill>/SKILL.md        Agent Skills (see aiws_skills.py)
    <plugin>/commands/<name>.md             a prompt template; `$ARGUMENTS` and `$1`..`$9` are filled in
    <plugin>/aiws.json                      AIWS-only extras: `guards` and `routeHints` (below)

What is used, and what is not (so nobody assumes a plugin can do more than it can):
  used     skills, commands, guards, routeHints
  listed   everything else a plugin ships, with the reason it is ignored: hooks (their commands are NEVER run), mcpServers
           (never started), agents, bin/, scripts/, output styles, LSP servers, workflows ... Nothing in a plugin is executed.

Safety rules
  * A user plugin is DISABLED until a person enables it, and the enable call must carry the tree hash that person was shown
    (so what was reviewed is what is enabled). Any change to any file afterwards disables it again.
  * System plugins live in the read-only image and are enabled only when their tree hash matches the pinned manifest.
  * Guards can only DENY (a tool, optionally for a path pattern). Route hints can only RAISE the cost tier. A plugin therefore
    can never widen what the agent may do; it can only make the agent more careful.
  * Bounded and flat: at most 64 files of at most 64 KiB, no symlinks, no hidden files except .claude-plugin, only .md/.json are read.
Standard library only; no network, no process is ever started from here.
"""
import fnmatch
import hashlib
import json
import os
import posixpath
import re
from pathlib import Path

import aiws_skills

SYSTEM_DIR = "/usr/local/share/aiws/plugins"
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
FILE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
MAX_FILES, MAX_FILE, MAX_TOTAL, MAX_DEPTH = 64, 64 * 1024, 512 * 1024, 5
MAX_PLUGINS, MAX_COMMAND, MAX_ARGS = 64, 4096, 500
READ_SUFFIXES = (".md", ".json")
# What a plugin may ship that we deliberately do not use, and why.
UNSUPPORTED_DIRS = {"hooks": "hook commands are never run", "agents": "plugin agents are not supported (cloud sub-agents are managed by the supervisor)",
                    "bin": "executables are never put on a path", "scripts": "scripts are never executed", "output-styles": "not supported",
                    "monitors": "not supported", "themes": "not supported", "workflows": "not supported"}
UNSUPPORTED_FILES = {".mcp.json": "MCP servers are never started", ".lsp.json": "language servers are not started from plugins"}
UNSUPPORTED_KEYS = {"hooks": UNSUPPORTED_DIRS["hooks"], "mcpServers": UNSUPPORTED_FILES[".mcp.json"], "lspServers": UNSUPPORTED_FILES[".lsp.json"],
                    "agents": UNSUPPORTED_DIRS["agents"], "outputStyles": "not supported", "workflows": "not supported", "dependencies": "not supported",
                    "userConfig": "not supported", "channels": "not supported", "experimental": "not supported"}
TOOL_PATTERN = re.compile(r"^[a-z0-9_.*?-]{1,64}$")
PATH_PATTERN = re.compile(r"^[A-Za-z0-9_./*?-]{1,128}$")


class PluginError(ValueError):
    """Safe to show to the user."""


def _is_repeated_group(pattern):
    """A regular expression that could backtrack for a very long time: a quantifier after a group, or a back-reference."""
    return bool(re.search(r"\)[+*{]|\\[1-9]|\(\?[=!<]", pattern))


def _walk(root):
    """(files, problems): every regular file under root as (relative posix path, Path), bounded, never following symlinks."""
    files, problems = [], []
    root = Path(root)
    base = len(root.parts)
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        here = Path(dirpath)
        if len(here.parts) - base > MAX_DEPTH:
            problems.append("folders are nested too deeply")
            dirnames[:] = []
            continue
        for name in list(dirnames):
            if (here / name).is_symlink():
                problems.append("symlink refused: " + name)
                dirnames.remove(name)
            elif not (FILE_NAME_RE.match(name) or name == ".claude-plugin"):
                problems.append("unusual folder name refused: " + name[:30])
                dirnames.remove(name)
        for name in filenames:
            p = here / name
            rel = p.relative_to(root).as_posix()
            if p.is_symlink() or not p.is_file():
                problems.append("not a regular file: " + rel[:60])
            elif not (FILE_NAME_RE.match(name) or name in (".mcp.json", ".lsp.json")):
                problems.append("unusual file name refused: " + rel[:60])
            else:
                files.append((rel, p))
            if len(files) > MAX_FILES:
                problems.append("more than %d files" % MAX_FILES)
                return files, problems
    return sorted(files), problems


def tree_hash(files):
    h = hashlib.sha256()
    for rel, path in files:
        h.update(rel.encode() + b"\0" + hashlib.sha256(path.read_bytes()).hexdigest().encode() + b"\n")
    return h.hexdigest()


def _json_file(path, limit=MAX_FILE):
    try:
        raw = path.read_bytes()
        if len(raw) > limit:
            raise PluginError("%s is larger than %d KiB" % (path.name, limit // 1024))
        doc = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise PluginError("%s is not valid JSON: %s" % (path.name, str(exc)[:60]))
    if not isinstance(doc, dict):
        raise PluginError(path.name + " must be a JSON object")
    return doc


def _inside(root, value):
    """A manifest path like "./extra-skills": relative, no .., must exist inside the plugin and not be a symlink."""
    if not isinstance(value, str) or not value.startswith("./") or ".." in value.split("/") or "\\" in value or len(value) > 120:
        raise PluginError("paths in plugin.json must look like ./folder")
    p = (root / value[2:])
    if p.is_symlink() or not p.exists() or not p.resolve().is_relative_to(root.resolve()):
        raise PluginError("path not found inside the plugin: " + value[:60])
    return p


def parse_command(text, known_tools):
    fields, body = ({}, text.strip())
    if text.startswith("---"):
        fields, body = aiws_skills.parse_frontmatter(text)
    if not body:
        raise PluginError("command has no text")
    if len(body.encode("utf-8")) > MAX_COMMAND:
        raise PluginError("command is larger than %d KiB" % (MAX_COMMAND // 1024))
    honored, ignored = aiws_skills.map_allowed_tools(fields.get("allowed-tools"), set(known_tools))
    shell = [l for l in body.splitlines() if l.lstrip().startswith("!") or re.search(r"!`", l)]
    return {"description": str(fields.get("description") or "")[:200], "argumentHint": str(fields.get("argument-hint") or "")[:80],
            "template": body, "allowedTools": honored, "ignoredTools": ignored, "shellLines": len(shell)}


def expand_command(command, args=""):
    """Fill `$ARGUMENTS` and `$1`..`$9`. Nothing else is substituted and nothing is executed: a `!` shell line stays plain text."""
    args = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", str(args or ""))[:MAX_ARGS].strip()
    words = args.split()
    text = command["template"].replace("$ARGUMENTS", args)
    text = re.sub(r"\$([1-9])", lambda m: words[int(m.group(1)) - 1] if int(m.group(1)) <= len(words) else "", text)
    return text[:MAX_COMMAND]


def _norm_path(value):
    """A path as a guard sees it: slashes only, `.`/`..` folded, no leading slash, lower case (so `.ENV` is `.env`).
    NOT lstrip("./"): that strips a leading dot as well and turned `.env` into `env`, which let dotfiles walk past the guard."""
    p = posixpath.normpath(str(value).replace("\\", "/")).lstrip("/")
    return "" if p == "." else p.lower()


def check_guards(guards, tool, args):
    """None when the call is allowed; otherwise the plugin's own reason for blocking it. Deny rules only."""
    paths = [_norm_path(args[k]) for k in ("path", "to") if isinstance(args, dict) and isinstance(args.get(k), str)]
    for g in guards:
        if not fnmatch.fnmatchcase(tool, g["tool"]):
            continue
        if g.get("path") is None or any(fnmatch.fnmatchcase(p, g["path"].lower()) for p in paths):
            return "blocked by plugin '%s': %s" % (g["plugin"], g["why"])
    return None


def _extras(root, problems):
    path = root / "aiws.json"
    guards, floors = [], []
    if not path.is_file():
        return guards, floors
    doc = _json_file(path)
    for g in (doc.get("guards") or [])[:20]:
        deny = g.get("deny") if isinstance(g, dict) else None
        if not isinstance(deny, dict) or not isinstance(deny.get("tool"), str) or not TOOL_PATTERN.match(deny["tool"]):
            problems.append("a guard needs deny.tool made of letters, digits . _ * ? -")
            continue
        p = deny.get("path")
        if p is not None and (not isinstance(p, str) or not PATH_PATTERN.match(p) or ".." in p):
            problems.append("a guard's deny.path is not a plain relative glob")
            continue
        guards.append({"tool": deny["tool"], "path": p, "why": str(g.get("why") or "no reason given")[:160]})
    for h in (doc.get("routeHints") or [])[:20]:
        pat, tier = (h.get("pattern"), h.get("tier")) if isinstance(h, dict) else (None, None)
        try:
            if not isinstance(pat, str) or not 1 <= len(pat) <= 120 or tier not in ("flash", "pro") or _is_repeated_group(pat):
                raise ValueError
            re.compile(pat)
        except (ValueError, re.error):
            problems.append("a routeHint needs a simple pattern (no repeated groups) and tier flash or pro")
            continue
        floors.append({"pattern": pat, "tier": tier, "why": str(h.get("why") or "")[:160]})
    return guards, floors


def load_plugin(root, source, known_tools=()):
    """One plugin folder -> a record. Never raises for a bad plugin: `valid` is False and `problems` says why."""
    root = Path(root)
    rec = {"name": root.name, "version": "", "description": "", "source": source, "treeSha256": None, "files": 0, "valid": False,
           "skills": [], "commands": {}, "guards": [], "floors": [], "ignored": [], "problems": [], "root": str(root)}
    try:
        if root.is_symlink() or not root.is_dir():
            raise PluginError("not a plain folder")
        files, walk_problems = _walk(root)
        if walk_problems:
            raise PluginError(walk_problems[0])
        total = 0
        for rel, p in files:
            size = p.stat().st_size
            total += size
            if size > MAX_FILE:
                raise PluginError("%s is larger than %d KiB" % (rel, MAX_FILE // 1024))
        if total > MAX_TOTAL:
            raise PluginError("the plugin is larger than %d KiB" % (MAX_TOTAL // 1024))
        rec["files"], rec["treeSha256"] = len(files), tree_hash(files)
        manifest_path = next((root / m for m in (".claude-plugin/plugin.json", "plugin.json") if (root / m).is_file()), None)
        manifest = _json_file(manifest_path) if manifest_path else {"name": root.name}
        name = manifest.get("name")
        if not isinstance(name, str) or not NAME_RE.match(name) or len(name) > 64:
            raise PluginError("name must be kebab-case, 1-64 characters")
        if name != root.name:
            raise PluginError("the folder name '%s' must equal the plugin name '%s'" % (root.name, name))
        rec.update(name=name, version=str(manifest.get("version") or "")[:32], description=str(manifest.get("description") or "")[:300])
        for key, why in UNSUPPORTED_KEYS.items():
            if key in manifest:
                rec["ignored"].append({"what": "plugin.json: " + key, "why": why})
        for rel, _ in files:
            top = rel.split("/")[0]
            if top in UNSUPPORTED_DIRS:
                rec["ignored"].append({"what": rel, "why": UNSUPPORTED_DIRS[top]})
            elif rel in UNSUPPORTED_FILES:
                rec["ignored"].append({"what": rel, "why": UNSUPPORTED_FILES[rel]})
            elif not rel.endswith(READ_SUFFIXES) and not rel.startswith(("skills/", "commands/")):
                rec["ignored"].append({"what": rel, "why": "only .md and .json files are read"})
        # skills: the default folder plus any extra folders named in plugin.json (Claude Code: "skills adds to the default scan")
        dirs = [root / "skills"]
        extra = manifest.get("skills")
        for value in ([extra] if isinstance(extra, str) else extra if isinstance(extra, list) else [])[:8]:
            dirs.append(_inside(root, value))
        seen = set()
        for d in dirs:
            found, bad, ignored = aiws_skills.load_dir_skills(d, known_tools)
            rec["problems"] += ["skill %s: %s" % (n, w) for n, w in bad]
            rec["ignored"] += [{"what": "skills/" + n, "why": w} for n, w in ignored]
            for s in found:
                if s["name"] in seen:
                    rec["problems"].append("skill %s is defined twice" % s["name"])
                    continue
                seen.add(s["name"])
                rec["skills"].append({**s, "id": "%s:%s" % (name, s["name"]), "source": "plugin:" + name, "trusted": False})
        # commands: flat files, or one folder level that becomes a `a:b` name segment (Claude Code naming)
        cdirs = [root / "commands"]
        cextra = manifest.get("commands")
        for value in ([cextra] if isinstance(cextra, str) else cextra if isinstance(cextra, list) else [])[:8]:
            cdirs.append(_inside(root, value))
        for d in cdirs:
            if not d.is_dir():
                continue
            for p in sorted(d.rglob("*.md"))[:64]:
                rel = p.relative_to(d).with_suffix("")
                segments = list(rel.parts)
                if len(segments) > 2 or not all(NAME_RE.match(s) for s in segments):
                    rec["problems"].append("command %s: names must be lowercase-with-hyphens, one folder deep" % rel.as_posix()[:40])
                    continue
                try:
                    cmd = parse_command(p.read_text(encoding="utf-8"), known_tools)
                except (OSError, UnicodeDecodeError, PluginError, aiws_skills.SkillError) as exc:
                    rec["problems"].append("command %s: %s" % (rel.as_posix()[:40], str(exc)[:80]))
                    continue
                cid = "%s:%s" % (name, ":".join(segments))
                if cmd["shellLines"]:
                    rec["ignored"].append({"what": "command " + cid, "why": "%d shell line(s) starting with ! are left as plain text, never executed" % cmd["shellLines"]})
                rec["commands"][cid] = {**cmd, "id": cid, "plugin": name}
        guards, floors = _extras(root, rec["problems"])
        rec["guards"] = [{**g, "plugin": name} for g in guards]
        rec["floors"] = [{**f, "plugin": name} for f in floors]
        rec["valid"] = True
    except (PluginError, OSError) as exc:
        rec["problems"].insert(0, str(exc)[:160])
    return rec


class PluginManager:
    def __init__(self, user_dir, state_path, system_dir=SYSTEM_DIR, known_tools=()):
        self.user_dir, self.system_dir = Path(user_dir), Path(system_dir)
        self.state_path = Path(state_path)
        self.known = set(known_tools)
        self.plugins = {}
        self.problems = []
        self.scan()

    # -- state ------------------------------------------------------------------------------------------------------
    def _state(self):
        empty = {"enabled": {}, "disabledSystem": []}
        p = self.state_path
        try:
            if p.is_symlink() or not p.is_file() or p.stat().st_size > 65536:
                return empty
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return empty
        if not isinstance(doc, dict):
            return empty
        enabled = doc.get("enabled") if isinstance(doc.get("enabled"), dict) else {}
        return {"enabled": {k: v for k, v in enabled.items() if isinstance(k, str) and isinstance(v, str) and re.fullmatch(r"[a-f0-9]{64}", v)},
                "disabledSystem": [x for x in (doc.get("disabledSystem") or []) if isinstance(x, str)][:64]}

    def _save(self, state):
        self.state_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = self.state_path.with_name(self.state_path.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.state_path)

    # -- discovery --------------------------------------------------------------------------------------------------
    def scan(self):
        self.plugins, self.problems = {}, []
        pinned = {}
        try:
            mp = self.system_dir / "manifest.json"
            if mp.is_file() and not mp.is_symlink() and mp.stat().st_size <= 65536:
                pinned = {k: v for k, v in json.loads(mp.read_text(encoding="utf-8")).items() if isinstance(k, str) and isinstance(v, str)}
        except (OSError, ValueError, AttributeError):
            pinned = {}
        state = self._state()
        for source, directory in (("system", self.system_dir), ("user", self.user_dir)):
            if not directory.is_dir() or directory.is_symlink():
                continue
            for entry in sorted(directory.iterdir(), key=lambda p: p.name)[:MAX_PLUGINS]:
                if not entry.is_dir() and not entry.is_symlink():
                    continue
                rec = load_plugin(entry, source, self.known)
                if rec["name"] in self.plugins:
                    rec["valid"] = False
                    rec["problems"].insert(0, "the name is already provided by the system" if self.plugins[rec["name"]]["source"] == "system" else "duplicate name")
                    self.problems.append((entry.name, rec["problems"][0]))
                    continue
                if not rec["valid"]:
                    rec["status"] = "invalid"
                elif source == "system":
                    if pinned.get(rec["name"]) != rec["treeSha256"]:
                        rec["valid"], rec["status"] = False, "invalid"
                        rec["problems"].insert(0, "not pinned in the system manifest (or changed after the image was built)")
                    else:
                        rec["status"] = "disabled" if rec["name"] in state["disabledSystem"] else "enabled"
                else:
                    want = state["enabled"].get(rec["name"])
                    rec["status"] = "enabled" if want == rec["treeSha256"] else ("changed" if want else "disabled")
                self.plugins[rec["name"]] = rec

    # -- views ------------------------------------------------------------------------------------------------------
    def list(self):
        out = []
        for name in sorted(self.plugins):
            r = self.plugins[name]
            out.append({"name": name, "version": r["version"], "description": r["description"], "source": r["source"], "status": r["status"],
                        "treeSha256": r["treeSha256"], "files": r["files"], "skills": [s["name"] for s in r["skills"]],
                        "skillDescriptions": {s["name"]: s["description"] for s in r["skills"]}, "commands": sorted(r["commands"]),
                        "guards": r["guards"] and [{"tool": g["tool"], "path": g["path"], "why": g["why"]} for g in r["guards"]] or [],
                        "routeHints": len(r["floors"]), "ignored": r["ignored"], "problems": r["problems"]})
        return out

    def _active(self):
        return [r for r in self.plugins.values() if r["valid"] and r["status"] == "enabled"]

    def active_skills(self, known_tools=None):
        out = []
        for r in self._active():
            for s in r["skills"]:
                out.append({**s, "trusted": True})
        return out

    def active_commands(self):
        return {cid: c for r in self._active() for cid, c in r["commands"].items()}

    def active_guards(self):
        return [g for r in self._active() for g in r["guards"]]

    def active_floors(self):
        return [f for r in self._active() for f in r["floors"]]

    def find_command(self, text):
        """`/plugin:name args` or `/name args` (when only one plugin has that name) -> (command, args) or (None, text)."""
        m = re.match(r"^/([a-z0-9:-]{1,100})(?:\s+(.*))?\Z", text.strip(), re.S)
        if not m:
            return None, text
        key, args = m.group(1), m.group(2) or ""
        cmds = self.active_commands()
        if key in cmds:
            return cmds[key], args
        short = [c for cid, c in cmds.items() if cid.split(":", 1)[1] == key]
        return (short[0], args) if len(short) == 1 else (None, text)

    # -- changes (each one is a person's decision) -------------------------------------------------------------------
    def enable(self, name, tree_sha256=None):
        r = self.plugins.get(name)
        if r is None or not r["valid"]:
            raise PluginError("No valid plugin with that name")
        state = self._state()
        if r["source"] == "system":
            state["disabledSystem"] = [x for x in state["disabledSystem"] if x != name]
        else:
            if tree_sha256 != r["treeSha256"]:
                raise PluginError("The plugin changed since it was shown to you (hash mismatch). Review it again.")
            state["enabled"][name] = r["treeSha256"]
        self._save(state)
        self.scan()
        return self.plugins[name]["status"]

    def disable(self, name):
        r = self.plugins.get(name)
        if r is None:
            raise PluginError("No plugin with that name")
        state = self._state()
        if r["source"] == "system":
            if name not in state["disabledSystem"]:
                state["disabledSystem"].append(name)
        else:
            state["enabled"].pop(name, None)
        self._save(state)
        self.scan()
        return self.plugins[name]["status"]
