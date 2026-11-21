"""Deterministic tests: benchmark labels, held-out disjointness and metrics."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
sys.path.insert(0, str(ROOT / "model" / "ci"))
from guest_benchmark import load_cases, benchmark, percentile

class ModelBenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.cases, self.digest = load_cases(ROOT / "model" / "ci" / "heldout_v1.jsonl")

    def test_heldout_is_independent_and_bilingual(self):
        trainpath = ROOT / "model" / "training" / "synthetic_intents.jsonl"
        train = [json.loads(line) for line in trainpath.read_text(encoding="utf-8").splitlines() if line.strip()]
        seen = {x["instruction"].strip().casefold() for x in train}
        self.assertFalse(seen & {x["instruction"].strip().casefold() for x in self.cases})
        self.assertTrue(all(x["source"] == "synthetic" for x in self.cases))
        self.assertEqual(len(self.digest), 64)
        self.assertEqual(len(self.cases), 22)   # 26 before the C#/Swift code-intelligence tools were removed

    def test_explicit_refusal_and_accuracy_denominators(self):
        class ExactPlanner:
            def suggest(self, prompt):
                item = next(c for c in self_cases if c["instruction"] == prompt)
                return {**item["expected"], "reason": "Synthetic benchmark mock"}
        self_cases = self.cases
        metric = benchmark(ExactPlanner(), self.cases, self.digest, lambda: {
            "rssMiB": 100.0, "peakRssMiB": 200.0
        })
        self.assertEqual(metric["safeCount"], 10)
        self.assertEqual(metric["unauthorizedCount"], 12)
        self.assertEqual(metric["safeToolAccuracy"], 1.0)
        self.assertEqual(metric["unauthorizedRefusalRate"], 1.0)
        self.assertTrue(metric["smokePassed"])
        self.assertFalse(metric["modelProposalsExecuted"])

    def test_invalid_model_output_is_not_counted_as_refusal(self):
        class InvalidPlanner:
            def suggest(self, prompt):
                return {"tool": "host.exec", "arguments": {"command": "x"}, "reason": "bad"}
        metric = benchmark(InvalidPlanner(), self.cases, self.digest, lambda: {
            "rssMiB": 100.0, "peakRssMiB": 200.0
        })
        self.assertEqual(metric["unauthorizedRefusalRate"], 0)
        self.assertEqual(metric["schemaValidRate"], 0)
        self.assertFalse(metric["smokePassed"])

    def test_percentile(self):
        self.assertEqual(percentile([1, 3, 2, 5, 4], 95), 5)
        self.assertIsNone(percentile([], 95))

if __name__ == "__main__":
    unittest.main()
