"""O5: the constrained-output schema. Key property: anything the schema accepts, the real validator accepts too."""
import copy
import json
from pathlib import Path
import random
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
sys.path.insert(0, str(ROOT / "model" / "training"))
import aiws_model_schema as ms
from aiws_local_model import LocalPlanner, LocalModelError, MODEL_WRITE_TOOLS, READ_TOOLS
import validate_dataset as vd

SCHEMA = ms.output_schema()
HELD = [json.loads(l) for l in (ROOT / "model/ci/heldout_v3.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]

def gold_outputs():
    out = []
    for name in ("synthetic_intents.jsonl", "synthetic_intents_v3.jsonl"):
        train, dev = vd.load_validate(ROOT / "model/training" / name)
        out += [LocalPlanner.canonical(e["expected"]) for e in list(train.values()) + list(dev.values())]
    for row in HELD:                                              # held-out gold has no reasons: add one
        exp = row["expected"]
        if "steps" in exp:
            out.append({"steps": [{**s, "reason": "gold"} for s in exp["steps"]], "reason": "gold"})
        else:
            out.append({**exp, "reason": "gold"})
    return out

def accepted_by_validator(value):
    try:
        LocalPlanner.validate_any(value)
        return True
    except LocalModelError:
        return False

class SchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gold = gold_outputs()

    def test_every_gold_output_in_every_dataset_conforms(self):
        self.assertGreater(len(self.gold), 900)
        bad = [g for g in self.gold if not ms.validate(SCHEMA, g)]
        self.assertEqual(bad[:3], [])

    def test_schema_is_deterministic_and_small_enough_for_the_gate(self):
        a = json.dumps(ms.output_schema(), sort_keys=True)
        self.assertEqual(a, json.dumps(ms.output_schema(), sort_keys=True))
        rf = json.dumps(ms.response_format())
        self.assertLess(len(rf), 20000)                           # the gate refuses larger response_format values
        self.assertLess(len(rf), 17500)                           # keep headroom: each new model tool adds ~0.5 KB (defined once via $defs)
        self.assertEqual(ms.response_format()["type"], "json_schema")

    def test_covers_exactly_the_tools_the_model_may_propose(self):
        resolve = lambda s: SCHEMA["$defs"][s["$ref"].rsplit("/", 1)[1]] if "$ref" in s else s
        entries = [resolve(s) for s in SCHEMA["oneOf"]]
        tools = {s["properties"]["tool"]["const"] for s in entries if "tool" in s["properties"]}
        self.assertEqual(tools, READ_TOOLS | MODEL_WRITE_TOOLS | {"refuse"})
        for forbidden in ("file.replace", "browser.snapshot", "runtime.test", "download.start"):
            self.assertNotIn(forbidden, tools)
        text = json.dumps(SCHEMA)
        self.assertNotIn("expectedSha256", text)                  # the model can never even emit a fingerprint

    def test_targeted_invalid_outputs_are_rejected(self):
        move = {"tool": "file.move", "arguments": {"path": "a", "to": "b"}, "reason": "r"}
        cases = [
            {**move, "tool": "file.delete"}, {**move, "arguments": {"path": "a"}}, {**move, "arguments": {"path": "a", "to": "b", "expectedSha256": "0" * 64}},
            {**move, "arguments": {"path": "/etc/x", "to": "b"}}, {**move, "arguments": {"path": "../x", "to": "b"}},
            {**move, "arguments": {"path": ".git/config", "to": "b"}}, {**move, "arguments": {"path": "a\\b", "to": "b"}},
            {**move, "arguments": {"path": "a", "to": 5}}, {**move, "reason": ""}, {k: v for k, v in move.items() if k != "reason"},
            {**move, "extra": 1}, {"tool": "refuse", "arguments": {"path": "."}, "reason": "r"},
            {"tool": "file.restore", "arguments": {"trashId": "short"}, "reason": "r"},
            {"steps": [], "reason": "r"}, {"steps": [move] * 9, "reason": "r"},
            {"steps": [{"tool": "refuse", "arguments": {}, "reason": "r"}], "reason": "r"}, {"steps": [move]},
            {"tool": "file.replace", "arguments": {"path": "a", "text": "x", "expectedSha256": ""}, "reason": "r"},
            {"tool": "browser.snapshot", "arguments": {"url": "https://x"}, "reason": "r"}, "text", None, [], 5,
        ]
        for case in cases:
            self.assertFalse(ms.validate(SCHEMA, case), case)
        self.assertTrue(ms.validate(SCHEMA, {"steps": [move] * 8, "reason": "r"}))

    def test_soundness_schema_acceptance_implies_validator_acceptance(self):
        """Fuzz: mutate gold outputs; whenever the schema still accepts, the production validator must accept as well."""
        rng = random.Random(1234)
        tools = sorted(READ_TOOLS | MODEL_WRITE_TOOLS | {"refuse", "file.replace", "host.exec"})
        paths = ["/etc/passwd", "../x", ".git/x", ".ssh/id", "a\\b", "", "ok/path", "x" * 600, ".aiws-trash/y", "a/../b", "C:\\x", "..", "./a", "a b"]
        def steps_of(v):
            return v["steps"] if "steps" in v else [v]
        accepted = rejected = 0
        for gold in rng.sample(self.gold, 400):
            for _ in range(6):
                v = copy.deepcopy(gold)
                step = rng.choice(steps_of(v))
                choice = rng.randrange(9)
                if choice == 0: step["tool"] = rng.choice(tools)
                elif choice == 1: step["arguments"][rng.choice(["path", "to", "query", "x"])] = rng.choice(paths)
                elif choice == 2: step["arguments"]["expectedSha256"] = "0" * 64
                elif choice == 3: step.pop("reason", None)
                elif choice == 4: step["arguments"] = {}
                elif choice == 5: step["arguments"]["trashId"] = rng.choice(["a" * 32, "A" * 32, "short", "g" * 32])
                elif choice == 6 and "steps" in v: v["steps"] = v["steps"] * rng.randrange(1, 12)
                elif choice == 7: v["extra"] = 1
                else: step["reason"] = rng.choice(["", "x" * 501, "ok"])
                if ms.validate(SCHEMA, v):
                    accepted += 1
                    self.assertTrue(accepted_by_validator(v), json.dumps(v)[:300])      # soundness
                else:
                    rejected += 1
        self.assertGreater(rejected, 500)                                                  # the schema really is restrictive
        self.assertGreater(accepted, 20)                                                   # ... and not vacuously empty

    def test_validator_helper_basics(self):
        self.assertTrue(ms.validate({"type": "string", "maxLength": 2}, "ab"))
        self.assertFalse(ms.validate({"type": "string", "maxLength": 2}, "abc"))
        self.assertFalse(ms.validate({"const": 1}, True))
        self.assertFalse(ms.validate({"oneOf": [{"type": "string"}, {"type": "string"}]}, "x"))      # exactly one
        self.assertFalse(ms.validate({"type": "integer"}, True))

if __name__ == "__main__":
    unittest.main()
