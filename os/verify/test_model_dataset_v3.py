"""Dataset v3 = v2 verbatim + the integrated tools (app.launch, doc.text, tools.list, ext.*) and their refusals."""
from collections import Counter
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
sys.path.insert(0, str(ROOT / "model" / "ci"))
sys.path.insert(0, str(ROOT / "model" / "training"))
import generate_dataset as gen2
import generate_dataset_v3 as gen3
import validate_dataset as vd
import aiws_apps
from guest_benchmark import load_cases, benchmark
from aiws_local_model import LocalPlanner, LocalModelError, MODEL_WRITE_TOOLS, READ_TOOLS, system_prompt

TRAIN2 = ROOT / "model/training/synthetic_intents_v2.jsonl"; HELD2 = ROOT / "model/ci/heldout_v2.jsonl"
TRAIN3 = ROOT / "model/training/synthetic_intents_v3.jsonl"; HELD3 = ROOT / "model/ci/heldout_v3.jsonl"
NEW_TOOLS = {"app.launch", "doc.text", "tools.list", "ext.rg", "ext.jq", "ext.gitlog", "ext.sqlite"}
MEM = lambda: {"rssMiB": 100.0, "peakRssMiB": 200.0}

class Oracle:
    def __init__(self, cases):
        self.by_text = {c["instruction"]: c["expected"] for c in cases}
    def suggest(self, prompt):
        exp = self.by_text[prompt]
        return ({"steps": [{**s, "reason": "gold"} for s in exp["steps"]], "reason": "gold"} if "steps" in exp else {**exp, "reason": "gold"})

def rows(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]

class V3Tests(unittest.TestCase):
    def test_committed_files_match_the_generator_and_v2_is_untouched(self):
        train, held = gen3.generate()
        self.assertEqual(TRAIN3.read_text(encoding="utf-8"), gen2.dump(train))
        self.assertEqual(HELD3.read_text(encoding="utf-8"), gen2.dump(held))
        t2, h2 = gen2.generate()
        self.assertEqual(TRAIN2.read_text(encoding="utf-8"), gen2.dump(t2))      # v2 files were NOT regenerated differently
        self.assertEqual(HELD2.read_text(encoding="utf-8"), gen2.dump(h2))
        self.assertTrue(TRAIN3.read_text(encoding="utf-8").startswith(TRAIN2.read_text(encoding="utf-8")))
        self.assertTrue(HELD3.read_text(encoding="utf-8").startswith(HELD2.read_text(encoding="utf-8")))

    def test_every_new_tool_has_enough_training_examples_in_both_languages(self):
        train, dev = vd.load_validate(TRAIN3)
        summary = vd.summarize(train, dev)
        for tool in NEW_TOOLS:
            self.assertGreaterEqual(summary["byTool"].get(tool, 0), 9, tool)
        by_lang = Counter()
        for entry in train.values():
            exp = entry["expected"]
            tools = [s["tool"] for s in exp["steps"]] if "steps" in exp else [exp["tool"]]
            for t in set(tools) & NEW_TOOLS:
                by_lang[(t, "zh" if any("一" <= c <= "鿿" for c in entry["instruction"]) else "en")] += 1
        for tool in NEW_TOOLS:
            for lang in ("zh", "en"):
                self.assertGreaterEqual(by_lang[(tool, lang)], 3, (tool, lang))

    def test_heldout_v3_is_a_valid_release_set_and_covers_the_new_tools(self):
        cases, digest = load_cases(HELD3, require_release=True)
        self.assertEqual(len(digest), 64); self.assertEqual(len(cases), 242 + 130)
        seen = Counter()
        for c in cases:
            exp = c["expected"]
            for s in (exp["steps"] if "steps" in exp else [exp]):
                seen[s["tool"]] += 1
        for tool in NEW_TOOLS:
            self.assertGreaterEqual(seen[tool], 4, tool)
        new = [c for c in cases if c["id"].startswith("hold-v3")]
        for kind in ("safe", "write", "plan", "unauthorized"):
            for lang in ("zh", "en"):
                self.assertGreaterEqual(sum(c["kind"] == kind and c["language"] == lang for c in new), 4, (kind, lang))

    def test_training_and_dev_never_overlap_any_locked_heldout_set(self):
        train, dev = vd.load_validate(TRAIN3)
        self.assertTrue(vd.check_independence(train, dev))                      # checks held v1, v2 AND v3
        self.assertIn(HELD3, vd.HELDOUT_FILES)

    def test_groups_use_disjoint_templates_and_vocabulary(self):
        for intent, groups in gen3.T.items():
            for lang in ("zh", "en"):
                self.assertFalse(set(groups["train"][lang]) & set(groups["held"][lang]), intent)
                self.assertFalse(set(groups["dev"][lang]) & set(groups["held"][lang]), intent)
        for name in ("DOCS", "JSONS", "REGEX", "DIRS", "DBS", "TABLES", "UNKNOWN_APPS", "FILES"):
            table = getattr(gen3, name)
            self.assertFalse(set(table["train"]) & set(table["held"]), name)
            self.assertFalse(set(table["dev"]) & set(table["held"]), name)
        for group in ("train", "dev"):
            for ident, names in gen3.APPS[group].items():
                for lang in ("zh", "en"):
                    self.assertFalse(set(names[lang]) & {n for v in gen3.APPS["held"].values() for n in v[lang]}, (ident, lang))

    def test_all_launch_targets_are_registered_gui_programs(self):
        for path in (TRAIN3, HELD3):
            for row in rows(path):
                exp = row["expected"]
                for s in (exp["steps"] if "steps" in exp else [exp]):
                    if s["tool"] == "app.launch":
                        aiws_apps.require_launchable(s["arguments"]["id"])
                        self.assertEqual(set(s["arguments"]), {"id"})

    def test_router_keeps_every_new_legitimate_request_local(self):
        """Regression on TRAIN/DEV phrasing only (the held-out v3 set was looked at once, with no rule changes made afterwards)."""
        from aiws_model_router import classify, DEFAULT_CONFIG
        config = json.loads(json.dumps(DEFAULT_CONFIG)); config["externalEnabled"] = True
        legit = [r for r in rows(TRAIN3) if r["id"].startswith(("train3", "dev3")) and r["expected"].get("tool") != "refuse"]
        local = sum(classify(r["instruction"], config, lambda exe: None)["route"] == "local" for r in legit)
        self.assertGreaterEqual(local / len(legit), 0.95)

    def test_launch_is_always_graded_as_a_write_that_needs_approval(self):
        checked = LocalPlanner.validate({"tool": "app.launch", "arguments": {"id": "terminal"}, "reason": "x"})
        self.assertEqual((checked["grade"], checked["requiresApproval"], checked["executed"]), ("write", True, False))
        self.assertIn("app.launch", MODEL_WRITE_TOOLS); self.assertNotIn("app.launch", READ_TOOLS)

    def test_model_proposals_outside_the_allowance_are_rejected(self):
        bad = [("app.launch", {"id": "git"}), ("app.launch", {"id": "viewer"}), ("app.launch", {"id": "terminal -e sh"}),
               ("app.launch", {"id": "terminal", "args": "-e sh"}), ("ext.jq", {"filter": "-n", "path": "a.json"}),
               ("ext.gitlog", {"count": "999"}), ("ext.gitlog", {"count": "x"}),
               ("ext.sqlite", {"path": "a.db", "query": "DROP TABLE t"}), ("ext.sqlite", {"path": "a.db", "query": "select 1; select 2"}),
               ("ext.sqlite", {"path": "../a.db", "query": "select 1"}), ("doc.text", {"path": "/etc/passwd"})]
        for tool, args in bad:
            with self.assertRaises(LocalModelError, msg=(tool, args)):
                LocalPlanner.validate({"tool": tool, "arguments": args, "reason": "x"})

    def test_system_prompt_names_the_launchable_programs_and_the_read_only_rule(self):
        prompt = system_prompt()
        for ident in ("terminal", "chromium", "aiws-code", "files-gui", "editor", "firefox"):
            self.assertIn(ident, prompt)
        self.assertNotIn("viewer", prompt.split("app.launch takes only id, one of:")[1].split(";")[0])
        self.assertIn("ext.* tools are read-only", prompt)
        self.assertLess(len(prompt), 3600)                                       # a long prompt costs tokens on EVERY request

    def test_release_gate_passes_for_an_oracle_and_fails_for_a_launch_everything_model(self):
        cases, digest = load_cases(HELD3, require_release=True)
        ok = benchmark(Oracle(cases), cases, digest, MEM, release=True)
        self.assertEqual((ok["safeToolAccuracy"], ok["unauthorizedRefusalRate"], ok["schemaValidRate"]), (1.0, 1.0, 1.0))
        self.assertTrue(ok["releaseEligibleDataset"] and ok["releasePassed"])

        class LaunchEverything:                       # the dangerous failure mode: never refuses, always opens a terminal
            def suggest(self, prompt):
                return {"tool": "app.launch", "arguments": {"id": "terminal"}, "reason": "x"}
        bad = benchmark(LaunchEverything(), cases, digest, MEM, release=True)
        self.assertFalse(bad["releasePassed"]); self.assertLess(bad["unauthorizedRefusalRate"], 0.5)

if __name__ == "__main__":
    unittest.main()
