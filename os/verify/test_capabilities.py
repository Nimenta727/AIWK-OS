"""Capability index: deterministic retrieval, pinned skills, quarantine, bounded secret-screened memory."""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
import aiws_capabilities as C

TOOLS = [("file.read", "Read a text file from the workspace"), ("file.move", "Move or rename a file or folder"),
         ("workspace.search", "Search file names and contents in the workspace"), ("network.status", "Show network interfaces and connections"),
         ("ext.git", "Show git status, log and diff of the workspace"), ("app.launch", "Start a desktop program such as the terminal"),
         ("system.info", "Report memory, disk and CPU usage")]
SKILL = "---\nname: tidy-downloads\ntitle: Tidy the downloads folder\nkeywords: 整理, 下载, cleanup\nrequires: file.move, workspace.search\n---\nGroup files by type into sub folders, never delete.\n"

def skill_dir(tmp, text=SKILL, name="tidy-downloads.md"):
    d = Path(tmp) / "skills"; d.mkdir(exist_ok=True); (d / name).write_text(text, encoding="utf-8"); return d

class RetrievalTests(unittest.TestCase):
    def caps(self, **kw):
        return C.Capabilities(TOOLS, **kw)
    def test_returns_a_small_relevant_subset(self):
        hits = self.caps().select("move this file to another folder", 3)
        self.assertEqual(hits[0]["id"], "tool:file.move"); self.assertLessEqual(len(hits), 3)
    def test_deterministic(self):
        c = self.caps()
        self.assertEqual(c.select("file", 5), c.select("file", 5))
    def test_chinese_query_matches_chinese_keywords(self):
        with tempfile.TemporaryDirectory() as t:
            c = C.Capabilities(TOOLS, skill_dirs=[(skill_dir(t), False)])
            self.assertEqual(c.select("帮我整理下载文件夹", 3)[0]["id"], "skill:tidy-downloads")
    def test_empty_and_nonsense_queries_return_nothing(self):
        c = self.caps()
        self.assertEqual(c.select("", 5), []); self.assertEqual(c.select("zzzqqq", 5), [])
    def test_k_is_bounded_and_kinds_validated(self):
        c = self.caps()
        self.assertLessEqual(len(c.select("file", 999)), 24)
        with self.assertRaises(C.CapabilityError):
            c.select("file", 3, ["hack"])
    def test_skill_pulls_in_its_declared_tools_only(self):
        with tempfile.TemporaryDirectory() as t:
            c = C.Capabilities(TOOLS, skill_dirs=[(skill_dir(t), False)])
            ids = [h["id"] for h in c.select("tidy downloads cleanup", 1)]
            self.assertEqual(ids[0], "skill:tidy-downloads"); self.assertIn("tool:file.move", ids)
            self.assertNotIn("tool:system.info", ids)

class SkillTests(unittest.TestCase):
    def test_pinned_hash_required_for_trusted_dir(self):
        with tempfile.TemporaryDirectory() as t:
            d = skill_dir(t); good = hashlib.sha256(SKILL.encode()).hexdigest()
            ok = C.Capabilities(TOOLS, skill_dirs=[(d, True)], pinned={"tidy-downloads": good})
            self.assertEqual(ok.counts()["skill"], 1)
            bad = C.Capabilities(TOOLS, skill_dirs=[(d, True)], pinned={"tidy-downloads": "0" * 64})
            self.assertEqual(bad.counts()["skill"], 0); self.assertEqual(bad.counts()["problems"], 1)
            unlisted = C.Capabilities(TOOLS, skill_dirs=[(d, True)], pinned={})
            self.assertEqual(unlisted.counts()["skill"], 0)
    def test_malformed_oversized_and_symlinked_skills_are_skipped(self):
        with tempfile.TemporaryDirectory() as t:
            d = skill_dir(t, "no front matter", "a.md")
            (d / "big.md").write_text("---\nname: big\n---\n" + "x" * 9000)
            (d / "bad.md").write_text("---\nname: Bad Name!\n---\nx")
            real = Path(t) / "real.md"; real.write_text(SKILL); (d / "link.md").symlink_to(real)
            c = C.Capabilities(TOOLS, skill_dirs=[(d, False)])
            self.assertEqual(c.counts()["skill"], 0); self.assertEqual(c.counts()["problems"], 4)

class MemoryTests(unittest.TestCase):
    def test_add_list_forget_and_dedupe(self):
        with tempfile.TemporaryDirectory() as t:
            m = C.MemoryStore(Path(t) / "mem.jsonl")
            a = m.add("User prefers dark theme", "preference"); self.assertEqual(m.add("User prefers dark theme", "preference")["id"], a["id"])
            self.assertEqual(len(m.list()), 1); m.forget(a["id"]); self.assertEqual(m.list(), [])
            with self.assertRaises(C.CapabilityError):
                m.forget("nope")
    def test_secrets_and_bad_input_refused(self):
        with tempfile.TemporaryDirectory() as t:
            m = C.MemoryStore(Path(t) / "mem.jsonl")
            for bad in ("my api_key is abc", "password: hunter2", "Bearer abcdef", "sk-abcdefghijklmnop", "", "x" * 401):
                with self.assertRaises(C.CapabilityError, msg=bad):
                    m.add(bad)
            with self.assertRaises(C.CapabilityError):
                m.add("ok", "weird")
    def test_memory_is_searchable_and_file_is_private(self):
        with tempfile.TemporaryDirectory() as t:
            m = C.MemoryStore(Path(t) / "s" / "mem.jsonl"); m.add("The project uses pnpm not npm", "project")
            c = C.Capabilities(TOOLS, memory=m)
            self.assertEqual(c.select("which package manager pnpm", 2, ["memory"])[0]["kind"], "memory")
            self.assertEqual((Path(t) / "s" / "mem.jsonl").stat().st_mode & 0o777, 0o600)
    def test_capacity_limit(self):
        with tempfile.TemporaryDirectory() as t:
            m = C.MemoryStore(Path(t) / "m.jsonl"); old = C.MAX_MEMORY; C.MAX_MEMORY = 2
            try:
                m.add("one"); m.add("two")
                with self.assertRaises(C.CapabilityError):
                    m.add("three")
            finally:
                C.MAX_MEMORY = old


# ---- HTTP layer ----
import http.client, json, os, threading, time
from unittest.mock import patch
from aiws_workbench import make_server, HOST

class CapabilityApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); base = Path(self.temp.name)
        self.root = (base / "workspace"); self.root.mkdir(); self.root = self.root.resolve()
        ui = base / "ui"; (ui / "assets").mkdir(parents=True); (ui / "index.html").write_text("<html><head></head><body></body></html>")
        self.env = patch.dict(os.environ, {"AIWS_WORKSPACE": str(self.root), "XDG_STATE_HOME": str(base / "state"), "AIWS_SKILLS_DIR": str(base / "noskills")}); self.env.start()
        self.cfgs = [patch("aiws_workbench.load_config", lambda: {"externalEnabled": False, "providers": {}, "extraLocalKeywords": [], "extraExternalKeywords": []}),
                     patch("aiws_workbench.load_builder_config", lambda: {"enabled": False, "envAllow": [], "isolation": {"mode": "none", "user": "x", "proxy": "http://127.0.0.1:3128"}})]
        [p.start() for p in self.cfgs]
        self.server = make_server(self.root, ui, 0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.hdr = {"X-AIWS-CSRF": json.loads(self.raw("GET", "/api/v1/session")[1])["csrf"]}
    def tearDown(self):
        self.server.shutdown(); self.server.server_close()
        a = self.server.application; a.pool.shutdown(wait=True, cancel_futures=True); time.sleep(0.2)
        a.tasks.close(); a.events.close(); a.mandates.close()
        [p.stop() for p in self.cfgs]; self.env.stop(); self.temp.cleanup()
    def raw(self, method, path, payload=None, headers=None):
        c = http.client.HTTPConnection(HOST, self.server.server_port, timeout=10)
        h = {"Host": HOST + ":" + str(self.server.server_port), **(headers or {})}
        body = None
        if payload is not None:
            body = json.dumps(payload); h["Content-Type"] = "application/json"
        c.request(method, path, body=body, headers=h); r = c.getresponse(); data = r.read(); c.close()
        return r.status, data
    def test_select_returns_small_ranked_set_from_real_catalogue(self):
        status, data = self.raw("GET", "/api/v1/capabilities?q=move+a+file&k=3")
        body = json.loads(data); self.assertEqual(status, 200)
        self.assertLessEqual(len(body["hits"]), 3); self.assertGreater(body["counts"]["tool"], 5)
        self.assertEqual(self.raw("GET", "/api/v1/capabilities?q=x&kind=hack")[0], 400)
        self.assertEqual(json.loads(self.raw("GET", "/api/v1/capabilities")[1])["hits"], [])
    def test_untrusted_skills_without_manifest_are_not_loaded(self):
        self.assertEqual(json.loads(self.raw("GET", "/api/v1/capabilities?q=file")[1])["counts"]["skill"], 0)
    def test_memory_round_trip_needs_csrf_and_refuses_secrets(self):
        self.assertEqual(self.raw("POST", "/api/v1/memory", {"text": "likes tabs"})[0], 403)
        status, data = self.raw("POST", "/api/v1/memory", {"text": "likes tabs", "kind": "preference"}, self.hdr)
        self.assertEqual(status, 202, data); mid = json.loads(data)["id"]
        self.assertEqual(len(json.loads(self.raw("GET", "/api/v1/memory")[1])["memory"]), 1)
        self.assertGreaterEqual(self.raw("POST", "/api/v1/memory", {"text": "my password is hunter2"}, self.hdr)[0], 400)
        self.assertEqual(self.raw("POST", "/api/v1/memory", {"text": "x", "extra": 1}, self.hdr)[0], 400)
        self.assertEqual(self.raw("POST", "/api/v1/memory", {"forget": mid}, self.hdr)[0], 202)
        self.assertEqual(json.loads(self.raw("GET", "/api/v1/memory")[1])["memory"], [])


class ShippedSkillTests(unittest.TestCase):
    """The skills in os/skills must load under the real pin check and may only name tools that exist."""
    def test_shipped_skills_load_pinned_and_require_real_tools(self):
        import json as _json
        import aiws_toolplane, aiws_workbench
        d = ROOT / "skills"
        pinned = _json.loads((d / "manifest.json").read_text())
        skills, problems = C.load_skill_dir(d, pinned)
        self.assertEqual(problems, []); self.assertGreaterEqual(len(skills), 5)
        known = {x["name"] for x in aiws_toolplane.catalog() if x["name"] in aiws_workbench.EXPOSED}
        for s in skills:
            self.assertTrue(set(s["requires"]) <= known, (s["name"], set(s["requires"]) - known))
            writes = set(s["requires"]) & aiws_toolplane.FILE_WRITE_TOOLS
            self.assertFalse(writes, "a shipped skill must not require write tools: " + s["name"])
    def test_manifest_is_current(self):
        import subprocess, json as _json
        before = (ROOT / "skills" / "manifest.json").read_text()
        with tempfile.TemporaryDirectory() as t:
            for f in (ROOT / "skills").glob("*.md"):
                (Path(t) / f.name).write_bytes(f.read_bytes())
            subprocess.run([sys.executable, str(ROOT / "skills" / "build_manifest.py"), t], check=True, capture_output=True)
            self.assertEqual(_json.loads((Path(t) / "manifest.json").read_text()), _json.loads(before), "run os/skills/build_manifest.py")
    def test_each_skill_is_found_by_its_own_purpose(self):
        import json as _json, aiws_toolplane, aiws_workbench
        d = ROOT / "skills"
        docs = [(x["name"], x["description"]) for x in aiws_toolplane.catalog() if x["name"] in aiws_workbench.EXPOSED]
        c = C.Capabilities(docs, skill_dirs=[(d, True)], pinned=_json.loads((d / "manifest.json").read_text()))
        for query, want in (("review what changed in the git diff", "skill:review-changes"), ("为什么没有网络 wifi 连不上", "skill:diagnose-network"),
                            ("电脑很卡 内存 磁盘", "skill:check-resources"), ("where is this function defined", "skill:find-in-project"),
                            ("总结这个项目 概览", "skill:summarize-project")):
            ids = [h["id"] for h in c.select(query, 3, ["skill"])]
            self.assertIn(want, ids, (query, ids))

if __name__ == "__main__":
    unittest.main()
