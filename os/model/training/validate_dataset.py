"""Validate the AIWS offline model dataset (zero model calls, zero network)."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"runtime"))
from aiws_local_model import LocalPlanner

def load_validate(path):
    train,evaluation,seen,phrases={}, {}, set(), set()
    for rownum,line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(),1):
        if not line.strip():
            continue
        row=json.loads(line)
        if not isinstance(row,dict) or set(row)!={"id","split","source","instruction","expected"}:
            raise ValueError("Invalid row schema at "+str(rownum))
        if row["id"] in seen or row["instruction"] in phrases:
            raise ValueError("Duplicate example or instruction")
        seen.add(row["id"]); phrases.add(row["instruction"])
        if row["source"] not in ("synthetic","authorized"):
            raise ValueError("Unknown sample provenance")
        if not isinstance(row["instruction"],str) or not 1<=len(row["instruction"])<=1000:
            raise ValueError("Invalid instruction length")
        validated=LocalPlanner.validate(row["expected"])
        if row["split"] not in ("train","eval"):
            raise ValueError("Invalid train/eval split")
        target=train if row["split"]=="train" else evaluation
        target[row["id"]]={"instruction":row["instruction"],"expected":validated}
    if not train or not evaluation:
        raise ValueError("Require train and held-out evaluation examples")
    return train,evaluation

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--dataset",default=str(Path(__file__).with_name("synthetic_intents.jsonl")))
    args=parser.parse_args()
    a,b=load_validate(args.dataset)
    print(json.dumps({"schema_pass":True,"train":len(a),"eval":len(b),
                      "weights_trained":False},sort_keys=True))

if __name__=="__main__":
    main()
