"""Dataset v2 (writes, plans, offline refusals), held-out independence and the release gate."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
sys.path.insert(0, str(ROOT / "model" / "ci"))
sys.path.insert(0, str(ROOT / "model" / "training"))
import generate_dataset as gen
import validate_dataset as vd
from guest_benchmark import load_cases, benchmark, RELEASE_LIMITS
from aiws_local_model import LocalPlanner, MODEL_WRITE_TOOLS, READ_TOOLS, system_prompt

HELD2 = ROOT / "model" / "ci" / "heldout_v2.jsonl"
HELD1 = ROOT / "model" / "ci" / "heldout_v1.jsonl"
TRAIN2 = ROOT / "model" / "training" / "synthetic_intents_v2.jsonl"
TRAIN1 = ROOT / "model" / "training" / "synthetic_intents.jsonl"
MEM = lambda: {"rssMiB": 100.0, "peakRssMiB": 200.0}

class Oracle:
    """Answers every case with its own gold label (what a perfect model would do)."""
    def __init__(self, cases):
        self.by_text = {c["instruction"]: c["expected"] for c in cases}
    def suggest(self, prompt):
        exp = self.by_text[prompt]
        if "steps" in exp:
            return {"steps": [{**s, "reason": "gold"} for s in exp["steps"]], "reason": "gold"}
        return {**exp, "reason": "gold"}

class DatasetV2Tests(unittest.TestCase):
    def test_committed_files_match_generator(self):
        train, held = gen.generate()
        self.assertEqual(TRAIN2.read_text(encoding="utf-8"), gen.dump(train))
        self.assertEqual(HELD2.read_text(encoding="utf-8"), gen.dump(held))

    def test_scale_and_balance(self):
        train, dev = vd.load_validate(TRAIN2)
        self.assertGreaterEqual(len(train), 600)
        self.assertGreaterEqual(len(dev), 60)
        cases, digest = load_cases(HELD2, require_release=True)
        self.assertEqual(len(digest), 64)
        self.assertGreaterEqual(len(cases), 200)
        unauthorized = [c for c in cases if c["kind"] == "unauthorized"]
        self.assertGreaterEqual(len(unauthorized), 80)
        for kind in ("safe", "write", "plan", "unauthorized"):
            for lang in ("zh", "en"):
                self.assertGreaterEqual(sum(c["kind"] == kind and c["language"] == lang for c in cases), 10, (kind, lang))
        summary = vd.summarize(train, dev)
        for tool in MODEL_WRITE_TOOLS | {"system.info", "network.status", "download.list", "download.progress", "file.trashList"}:
            self.assertGreater(summary["byTool"].get(tool, 0), 8, tool)
        self.assertGreater(summary["byTool"]["plan"], 60)
        self.assertGreater(summary["byTool"]["refuse"], 100)

    def test_all_training_targets_are_production_valid_and_safe(self):
        for path in (TRAIN1, TRAIN2):
            train, dev = vd.load_validate(path)
            for entry in list(train.values()) + list(dev.values()):
                exp = entry["expected"]
                steps = exp["steps"] if "steps" in exp else [exp]
                for s in steps:
                    self.assertNotIn("expectedSha256", s["arguments"])
                    self.assertTrue(s["tool"] in READ_TOOLS | MODEL_WRITE_TOOLS | {"refuse"}, s["tool"])
                    self.assertNotIn(s["tool"], ("file.replace", "browser.snapshot", "runtime.test"))

    def test_heldout_is_independent_of_all_training_and_dev_data(self):
        for path in (TRAIN1, TRAIN2):
            train, dev = vd.load_validate(path)
            self.assertTrue(vd.check_independence(train, dev))
        v1 = {json.loads(l)["instruction"].strip().casefold() for l in HELD1.read_text(encoding="utf-8").splitlines() if l.strip()}
        v2 = {json.loads(l)["instruction"].strip().casefold() for l in HELD2.read_text(encoding="utf-8").splitlines() if l.strip()}
        self.assertFalse(v1 & v2)

    def test_group_split_uses_disjoint_vocabulary_and_templates(self):
        files = lambda g: set(gen.VOCAB[g]["files"])
        self.assertFalse(files("train") & files("held"))
        self.assertFalse(files("dev") & files("held"))
        self.assertFalse(set(gen.VOCAB["train"]["dirs"]) & set(gen.VOCAB["held"]["dirs"]))
        for table in (gen.READ, gen.WRITE, gen.PLANS):
            for intent, groups in table.items():
                for lang in ("zh", "en"):
                    self.assertFalse(set(groups["train"][lang]) & set(groups["held"][lang]), intent)
                    self.assertFalse(set(groups["dev"][lang]) & set(groups["held"][lang]), intent)

    def test_independence_check_detects_leaks(self):
        leak = {"x": {"instruction": "Read utils.js now", "expected": {}}}
        with self.assertRaises(ValueError):
            vd.check_independence(leak, heldout=["read utils.js now"])
        near = {"x": {"instruction": "Show me the contents of the file budget.csv", "expected": {}}}
        with self.assertRaises(ValueError):
            vd.check_independence(near, heldout=["Show me the contents of the file budget.csv please"])
        self.assertTrue(vd.check_independence({"x": {"instruction": "totally different", "expected": {}}}, heldout=["read utils.js"]))

    def test_release_gate_with_oracle_and_with_bad_models(self):
        cases, digest = load_cases(HELD2, require_release=True)
        ok = benchmark(Oracle(cases), cases, digest, MEM, release=True)
        self.assertEqual((ok["safeToolAccuracy"], ok["safeArgumentAccuracy"], ok["unauthorizedRefusalRate"], ok["schemaValidRate"]),
                         (1.0, 1.0, 1.0, 1.0))
        self.assertTrue(ok["releaseEligibleDataset"] and ok["releasePassed"])
        self.assertEqual(set(ok["byKind"]), {"safe", "write", "plan", "unauthorized"})
        self.assertEqual(ok["criteria"], RELEASE_LIMITS)

        class NeverRefuses(Oracle):
            def suggest(self, prompt):
                got = Oracle.suggest(self, prompt)
                return {"tool": "workspace.tree", "arguments": {"path": "."}, "reason": "x"} if got["tool"] == "refuse" else got
        bad = benchmark(NeverRefuses(cases), cases, digest, MEM, release=True)
        self.assertLess(bad["unauthorizedRefusalRate"], 0.05)
        self.assertFalse(bad["releasePassed"])

        class ReversesPlans(Oracle):
            def suggest(self, prompt):
                got = Oracle.suggest(self, prompt)
                if "steps" in got:
                    got["steps"] = list(reversed(got["steps"]))
                return got
        rev = benchmark(ReversesPlans(cases), cases, digest, MEM, release=True)
        self.assertEqual(rev["byKind"]["plan"]["toolAccuracy"], 0.0)     # order is part of correctness
        self.assertFalse(rev["releasePassed"])

        class DropsWrites(Oracle):
            def suggest(self, prompt):
                got = Oracle.suggest(self, prompt)
                if got.get("tool") in MODEL_WRITE_TOOLS:
                    got["arguments"] = {k: v for k, v in got["arguments"].items() if k == "path"}
                return got
        dropped = benchmark(DropsWrites(cases), cases, digest, MEM, release=True)
        self.assertLess(dropped["byKind"]["write"]["argumentAccuracy"], 1.0)

    def test_small_set_can_never_pass_release_gate(self):
        cases, digest = load_cases(HELD1)
        class V1Oracle(Oracle):
            pass
        m = benchmark(V1Oracle(cases), cases, digest, MEM, release=True)
        self.assertFalse(m["releaseEligibleDataset"])
        self.assertFalse(m["releasePassed"])
        with self.assertRaises(ValueError):
            load_cases(HELD1, require_release=True)

    def test_training_and_inference_share_one_prompt(self):
        text = system_prompt()
        for needle in ("no network access", "steps", "cannot access the internet", "Never include expectedSha256",
                       "permanent deletion", "tool='refuse'"):
            self.assertIn(needle, text)
        for tool in sorted(MODEL_WRITE_TOOLS):
            self.assertIn(tool, text)
        self.assertNotIn("file.replace", text.split("File tools")[1])
        source = (ROOT / "model" / "training" / "train_lora.py").read_text(encoding="utf-8")
        self.assertIn("system_prompt()", source)
        self.assertIn("check_independence(rows,holdout)", source)

if __name__ == "__main__":
    unittest.main()
