"""Validate the AIWS offline model datasets (zero model calls, zero network).

Checks schema, provenance, uniqueness, production-schema validity (single proposals AND
multi-step plans, including the real stage builder), and independence between training data
and the locked held-out sets (exact and near-duplicate instructions).
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "runtime"))
from aiws_local_model import LocalPlanner, stages_from_proposal

NEAR_DUPLICATE = 0.8
HELDOUT_FILES = (HERE.parent / "ci" / "heldout_v1.jsonl", HERE.parent / "ci" / "heldout_v2.jsonl")

def _bigrams(text):
    compact = "".join(str(text).casefold().split())
    return {compact[i:i + 2] for i in range(max(1, len(compact) - 1))}

def similarity(a, b):
    x, y = _bigrams(a), _bigrams(b)
    return len(x & y) / max(1, len(x | y))

def _stub_stat(path):
    return {"sha256": "0" * 64}

def load_validate(path):
    train, evaluation, seen, phrases = {}, {}, set(), set()
    for rownum, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict) or set(row) != {"id", "split", "source", "instruction", "expected"}:
            raise ValueError("Invalid row schema at " + str(rownum))
        if row["id"] in seen or row["instruction"].strip().casefold() in phrases:
            raise ValueError("Duplicate example or instruction")
        seen.add(row["id"]); phrases.add(row["instruction"].strip().casefold())
        if row["source"] not in ("synthetic", "authorized"):
            raise ValueError("Unknown sample provenance")
        if not isinstance(row["instruction"], str) or not 1 <= len(row["instruction"]) <= 1000:
            raise ValueError("Invalid instruction length")
        validated = LocalPlanner.validate_any(row["expected"])
        if "steps" in validated:
            stages_from_proposal(validated, _stub_stat)   # the real stage builder must accept it
        if row["split"] not in ("train", "eval"):
            raise ValueError("Invalid train/eval split")
        target = train if row["split"] == "train" else evaluation
        target[row["id"]] = {"instruction": row["instruction"], "expected": validated}
    if not train or not evaluation:
        raise ValueError("Require train and held-out evaluation examples")
    return train, evaluation

def heldout_instructions(paths=HELDOUT_FILES):
    out = []
    for path in paths:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line)["instruction"])
    return out

def check_independence(*datasets, heldout=None):
    """No training/dev instruction may equal or nearly equal a locked held-out instruction."""
    held = heldout_instructions() if heldout is None else heldout
    exact = {h.strip().casefold() for h in held}
    for dataset in datasets:
        for entry in dataset.values():
            text = entry["instruction"]
            if text.strip().casefold() in exact:
                raise ValueError("Training instruction duplicates a held-out case")
            for h in held:
                if similarity(text, h) >= NEAR_DUPLICATE:
                    raise ValueError("Training instruction is a near-duplicate of a held-out case")
    return True

def summarize(*datasets):
    tools, langs = Counter(), Counter()
    for dataset in datasets:
        for entry in dataset.values():
            exp = entry["expected"]
            tools["plan" if "steps" in exp else exp["tool"]] += 1
            langs["zh" if any("一" <= c <= "鿿" for c in entry["instruction"]) else "en"] += 1
    return {"byTool": dict(sorted(tools.items())), "byLanguage": dict(langs)}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default=str(HERE / "synthetic_intents_v2.jsonl"))
    args = parser.parse_args()
    a, b = load_validate(args.dataset)
    check_independence(a, b)
    print(json.dumps({"schema_pass": True, "train": len(a), "eval": len(b), "independent_of_heldout": True,
                      "weights_trained": False, **summarize(a, b)}, sort_keys=True))

if __name__ == "__main__":
    main()
