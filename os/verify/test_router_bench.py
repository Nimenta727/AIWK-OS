"""Router/log benchmark: dataset shape and the invariants that make its numbers meaningful (no model, no llama.cpp needed)."""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("router_bench", ROOT / "model/bench/router_bench.py")
B = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)


def load(name):
    return [json.loads(l) for l in (ROOT / "model/ci" / name).read_text(encoding="utf-8").splitlines() if l.strip()]


class Datasets(unittest.TestCase):
    def test_shape_and_balance(self):
        for name, per in (("router_v1.jsonl", 30), ("router_v2_heldout.jsonl", 20)):
            rows = load(name)
            for tier in B.TIERS:
                self.assertEqual(sum(r["tier"] == tier for r in rows), per, (name, tier))
            self.assertTrue(all(set(r) == {"text", "tier"} and r["text"].strip() for r in rows))

    def test_heldout_does_not_overlap_the_tuning_set(self):
        a = {r["text"].strip().lower() for r in load("router_v1.jsonl")}
        b = {r["text"].strip().lower() for r in load("router_v2_heldout.jsonl")}
        self.assertFalse(a & b)

    def test_no_duplicates_and_both_languages(self):
        for name in ("router_v1.jsonl", "router_v2_heldout.jsonl"):
            texts = [r["text"] for r in load(name)]
            self.assertEqual(len(texts), len(set(texts)))
            zh = sum(any("一" <= ch <= "鿿" for ch in t) for t in texts)
            self.assertTrue(0.25 < zh / len(texts) < 0.75, name)


class Logs(unittest.TestCase):
    def test_generator_is_seeded(self):
        self.assertEqual(B.make_logs(7), B.make_logs(7))
        self.assertNotEqual(B.make_logs(7)[0]["lines"], B.make_logs(8)[0]["lines"])

    def test_root_cause_survives_compression_and_baselines_behave(self):
        cases = B.make_logs()
        self.assertEqual(len(cases), 12)
        for c in cases:
            items, text = B.compress(c["lines"])
            gold = set(c["gold"])
            self.assertTrue(gold & {i[0] for i in items}, c["id"])          # nothing to find if compression drops it
            self.assertLess(len(items), len(c["lines"]) / 3)
            self.assertLessEqual(len(text), 7000)
            self.assertFalse(gold & set(B.baseline_tail(items)), c["id"])   # the root cause is never just "the last lines"
            self.assertEqual(bool(gold & set(B.baseline_grep(items))), not c["hard"], c["id"])   # grep works only when not misleading

    def test_gold_line_numbers_point_at_the_gold_text(self):
        known = {g for k in B.KINDS for key in ("hard_gold", "easy_gold") for g in k[key]}
        for c in B.make_logs():
            for n in c["gold"]:
                self.assertIn(c["lines"][n - 1].split(" ", 2)[2], known, c["id"])      # drop the "date time" prefix

    def test_compress_keeps_first_line_number_and_counts_repeats(self):
        items, text = B.compress(["2025-01-01 00:00:00 INFO a 1", "2025-01-01 00:00:01 INFO a 2", "2025-01-01 00:00:02 ERROR boom"])
        self.assertEqual([(i[0], i[1]) for i in items], [(1, 2), (3, 1)])
        self.assertIn("L1 x2", text)

    def test_compress_budget_keeps_rare_lines(self):
        lines = ["2025-01-01 00:00:00 INFO common %d" % i for i in range(500)] + ["2025-01-01 00:00:00 FATAL unique-%s thing" % chr(97 + k) for k in range(40)]
        items, text = B.compress(lines, budget_chars=800)
        self.assertLessEqual(len(text), 800)
        self.assertTrue(all("FATAL" in i[2] or i[1] > 1 for i in items))


class Scoring(unittest.TestCase):
    def test_routing_score_counts_under_and_over_route(self):
        rows = [{"text": "a", "gold": "pro", "pred": "flash", "sec": 1}, {"text": "b", "gold": "local", "pred": "pro", "sec": 3},
                {"text": "中文", "gold": "flash", "pred": "flash", "sec": 2}, {"text": "d", "gold": "pro", "pred": "pro", "sec": 2}]
        s = B.score_routing(rows)
        self.assertEqual((s["accuracy"], s["underRoute"], s["overRoute"], s["proRecall"]), (0.5, 0.25, 0.25, 0.5))
        self.assertEqual(s["accuracyZh"], 1.0)

    def test_prompts_name_every_tier_and_are_stable(self):
        for p in (B.ROUTER_SYSTEM, B.ROUTER_SYSTEM_B):
            for t in B.TIERS:
                self.assertIn(t + ":", p)
        self.assertTrue(B.chat("s", "u").endswith("</think>\n\n"))        # non-thinking mode, no template engine needed


if __name__ == "__main__":
    unittest.main()
