"""Tier router: prompt pinned to the benchmark, rules only raise, explanations in both languages, safe fallbacks, honest counters."""
import importlib.util
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
sys.path.insert(0, str(ROOT / "verify" / "fixtures"))
import aiws_deepseek
import aiws_llm as L
import aiws_route as R
from fake_llm import FakeLLM, reply

spec = importlib.util.spec_from_file_location("router_bench", ROOT / "model/bench/router_bench.py")
BENCH = importlib.util.module_from_spec(spec)
spec.loader.exec_module(BENCH)


def rows(name):
    return [json.loads(l) for l in (ROOT / "model/ci" / name).read_text(encoding="utf-8").splitlines() if l.strip()]


def tier(t):
    return reply(json.dumps({"tier": t}))


class Pinned(unittest.TestCase):
    def test_the_shipped_prompt_is_exactly_the_one_the_benchmark_measured(self):
        self.assertEqual(R.PROMPT, BENCH.ROUTER_SYSTEM_B)

    def test_cloud_choice_uses_the_one_model_list(self):
        self.assertIsNone(R.cloud_choice("local"))
        self.assertEqual(R.cloud_choice("flash"), {"provider": "deepseek", "model": aiws_deepseek.MODELS[0], "thinking": False})
        self.assertEqual(R.cloud_choice("pro"), {"provider": "deepseek", "model": aiws_deepseek.MODELS[-1], "thinking": True})

    def test_every_explanation_exists_in_both_languages(self):
        for key, both in R.WHY.items():
            self.assertEqual(set(both), {"zh", "en"}, key)
            self.assertTrue(all(both.values()))


class Floors(unittest.TestCase):
    def test_rules_never_raise_a_request_above_what_a_person_labelled_it(self):
        for name in ("router_v1.jsonl", "router_v2_heldout.jsonl", "router_v3_fresh.jsonl"):
            for r in rows(name):
                floor, markers = R.floor_for(r["text"])
                if floor is not None:
                    self.assertLessEqual(R.RANK[floor], R.RANK[r["tier"]], (name, r["text"], markers))

    def test_clear_markers_raise_in_both_languages(self):
        for text, tier_, marker in (("fix this ```python\nx=1\n```", "flash", "code-block"), ("Traceback (most recent call last):\n File", "flash", "stack-trace"),
                                    ("write a function that sorts", "flash", "code-task"), ("帮我写一个函数", "flash", "code-task-zh"),
                                    ("the service deadlocks intermittently", "pro", None), ("线上偶尔会卡死", "pro", "hard-bug-zh"), ("设计一个缓存方案", "pro", "design-zh"),
                                    ("migrate the database to postgres 16", "pro", "design"), ("find the vulnerability in this", "pro", "security"), ("这里有个安全审计问题", "pro", "security")):
            floor, markers = R.floor_for(text)
            self.assertEqual(floor, tier_, (text, markers))
            if marker:
                self.assertIn(marker, markers)

    def test_plain_file_requests_trigger_nothing(self):
        for text in ("list files in docs", "把 logs 目录里最新的三个文件列出来", "show me the contents of requirements.txt", "整理一下下载文件夹", "move report.pdf into docs",
                     "what's the size of dist.zip", "打开 Makefile", "copy config.yaml to a backup"):
            self.assertEqual(R.floor_for(text), (None, []), text)

    def test_plugin_hints_can_only_raise_and_a_broken_one_is_ignored(self):
        hints = [{"pattern": "invoice|payment", "tier": "pro", "plugin": "billing"}, {"pattern": "[", "tier": "pro", "plugin": "broken"}, {"tier": "pro"}]
        self.assertEqual(R.floor_for("process the payment run", hints), ("pro", ["plugin:billing"]))
        self.assertEqual(R.floor_for("list the files", hints), (None, []))

    def test_the_patterns_cannot_be_made_to_run_for_long(self):
        for evil in ("a" * 1000, "fix " * 250, "(" * 500 + ")" * 500, "why " * 250, "```" * 300, "写" * 1000, ("fix the " + "x " * 20) * 20):
            t = time.monotonic()
            R.floor_for(evil)
            self.assertLess(time.monotonic() - t, 0.5, evil[:20])


class Decide(unittest.TestCase):
    def setUp(self):
        self.srv = FakeLLM().__enter__()
        self.addCleanup(self.srv.__exit__, None, None, None)
        self.llm = L.LocalLLM(self.srv.url, timeout=10)

    def decide(self, text, answer=None, **kw):
        if answer:
            self.srv.push(tier(answer))
        return R.decide(text, self.llm, **kw)

    def test_the_model_chooses_and_the_decision_carries_everything_the_ui_needs(self):
        d = self.decide("list the files in docs", "local")
        self.assertEqual((d["tier"], d["thinking"], d["cloud"], d["source"]), ("local", False, None, "model"))
        self.assertNotIn("final", d); self.assertNotIn("forbidden", d)                      # no hard "stay local" rule exists any more
        self.assertEqual(set(d["why"]), {"zh", "en"})
        sent = self.srv.requests[0]["messages"]
        self.assertEqual((sent[0], sent[1]["content"]), ({"role": "system", "content": R.PROMPT}, "list the files in docs"))
        self.assertEqual(self.srv.requests[0]["max_tokens"], 20)
        self.assertEqual(self.decide("write a quick script", "flash")["cloud"]["model"], aiws_deepseek.MODELS[0])
        d = self.decide("design a sync protocol", "pro")
        self.assertEqual((d["thinking"], d["cloud"]["thinking"]), (True, True))
        self.assertIsNotNone(d["usage"])

    def test_a_rule_raises_the_tier_and_says_so_in_both_languages(self):
        d = self.decide("write a function that parses dates", "local")
        self.assertEqual((d["tier"], d["modelTier"], d["floor"]), ("flash", "local", "flash"))
        self.assertIn("code-task", d["markers"])
        self.assertIn("local to flash", d["why"]["en"])
        self.assertIn("从 local 提高到 flash", d["why"]["zh"])
        d = self.decide("the job deadlocks intermittently, why", "flash")
        self.assertEqual((d["tier"], d["thinking"]), ("pro", True))

    def test_rules_never_lower_what_the_model_chose(self):
        d = self.decide("write a function", "pro")
        self.assertEqual((d["tier"], d["modelTier"]), ("pro", "pro"))
        self.assertNotIn("raised", json.dumps(d["why"]))
        self.assertEqual(self.decide("design the architecture", "flash")["tier"], "pro")        # raised, not lowered

    def test_sensitive_words_only_advise_and_never_change_the_tier(self):
        # Measured: ten of ten ordinary programmer requests mention something a "forbidden" rule knows (curl, ssh, fetch, upload, host, chmod ...).
        # A hard rule would have kept normal coding work off the cloud, so the router lists them as advisories and decides as usual.
        for text, cat in (("write a script that downloads a file from https://example.com/data.csv with curl", "network"), ("fix the ssh config parsing bug in config.py", "network"),
                          ("implement a fetch wrapper with retries in TypeScript", "network"), ("explain what chmod 755 does in this script", "shell_root"),
                          ("把结果上传到 S3 的函数怎么写", "cloud_or_exfil"), ("add a function to insert a row at the end of the table", "write_content")):
            d = self.decide(text, "flash")
            self.assertEqual((d["tier"], d["source"]), ("flash", "model"), text)
            self.assertIn(cat, d["advisories"], text)
            self.assertIn("approval", d["why"]["en"]); self.assertIn("批准", d["why"]["zh"])
            self.assertEqual(self.srv.requests[-1]["messages"][1]["content"], text)           # the model was asked, as for any request
        d = self.decide("list the files in docs", "local")
        self.assertEqual(d["advisories"], [])
        self.assertNotIn("approval", d["why"]["en"])

    def test_without_the_model_the_answer_is_flash_unless_a_rule_says_more_and_it_says_so(self):
        d = R.decide("rename the variable tmp", L.LocalLLM("http://127.0.0.1:1", timeout=2))
        self.assertEqual((d["tier"], d["source"], d["modelTier"]), ("flash", "rules-fallback", None))
        self.assertIn("not available", d["why"]["en"]); self.assertIn("不可用", d["why"]["zh"])
        self.assertEqual(R.decide("find the root cause of the memory leak", L.LocalLLM("http://127.0.0.1:1", timeout=2))["tier"], "pro")
        d = R.decide("list the files", None)
        self.assertEqual((d["tier"], d["source"]), ("flash", "rules"))

    def test_a_model_that_returns_garbage_falls_back_instead_of_crashing(self):
        self.srv.push(reply("not json"), reply("still not json"))
        d = R.decide("list the files", self.llm)
        self.assertEqual((d["tier"], d["source"]), ("flash", "rules-fallback"))
        self.srv.push(reply('{"tier":"enormous"}'), reply('{"tier":"huge"}'))
        self.assertEqual(R.decide("hello", self.llm)["source"], "rules-fallback")

    def test_bad_input_is_refused(self):
        for bad in ("", "   ", "x" * 1001, None, 5):
            with self.assertRaises(ValueError):
                R.decide(bad, self.llm)


class Stats(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.path = Path(self.t.name) / "s" / "route.json"
        self.s = R.RouteStats(self.path)

    def dec(self, final, model=None, source="model"):
        return {"tier": final, "modelTier": model or final, "source": source}

    def test_counters_and_rates(self):
        self.assertEqual(self.s.get()["decisions"], 0)
        self.assertIsNone(self.s.get()["overrideRate"])
        for d in (self.dec("local"), self.dec("flash"), self.dec("pro", "flash"), self.dec("flash", None, "rules-fallback")):
            self.s.record(d)
        self.s.override("flash", "pro"); self.s.override("flash", "pro"); self.s.override("pro", "local")
        for o in ("final", "proposed", "refused", "error"):
            self.s.completed_locally(o)
        g = self.s.get()
        self.assertEqual((g["decisions"], g["local"], g["flash"], g["pro"], g["raisedByRule"], g["fallback"]), (4, 1, 2, 1, 1, 1))
        self.assertEqual((g["overrides"], g["overrideMatrix"], g["overrideRate"]), (3, {"flash>pro": 2, "pro>local": 1}, 0.75))
        self.assertEqual((g["localCompleted"], g["localRefused"], g["localShare"]), (2, 1, 0.25))
        self.assertEqual(R.RouteStats(self.path).get()["decisions"], 4)                       # persisted
        self.assertEqual(oct(self.path.stat().st_mode & 0o777), "0o600")

    def test_invalid_overrides_and_damaged_files(self):
        for bad in (("flash", "flash"), ("x", "pro"), ("local", None)):
            with self.assertRaises(ValueError):
                self.s.override(*bad)
        self.path.parent.mkdir(parents=True)
        for content in ("not json", "[]", json.dumps({"decisions": -5, "local": True, "overrideMatrix": {"evil>key": 3, "flash>pro": "x"}})):
            self.path.write_text(content)
            g = self.s.get()
            self.assertEqual((g["decisions"], g["local"], g["overrideMatrix"]), (0, 0, {}))
        real = Path(self.t.name) / "real.json"
        real.write_text(json.dumps({"decisions": 99}))
        self.path.unlink(); self.path.symlink_to(real)
        self.assertEqual(self.s.get()["decisions"], 0)                                        # a symlink is not believed


if __name__ == "__main__":
    unittest.main()
