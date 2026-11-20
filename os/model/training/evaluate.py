"""Model benchmark: default schema-only, --live uses guest-only loopback."""
import argparse
import json
from pathlib import Path
import sys
from validate_dataset import load_validate

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"runtime"))
from aiws_guest_boundary import require_guest_runtime
from aiws_local_model import LocalPlanner

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--dataset",default=str(Path(__file__).with_name("synthetic_intents.jsonl")))
    parser.add_argument("--live",action="store_true")
    parser.add_argument("--report",default="aiws-model-eval.json")
    args=parser.parse_args()
    train,evals=load_validate(args.dataset)
    if not args.live:
        print(json.dumps({"schema_pass":True,"train":len(train),"eval":len(evals),
                          "inference_executed":False}))
        return
    require_guest_runtime()
    planner=LocalPlanner(enabled=True)
    results=[]
    for example in evals.values():
        try:
            suggestion=planner.suggest(example["instruction"])
            results.append({"valid":True,
                "tool_match":suggestion["tool"]==example["expected"]["tool"],
                "args_match":suggestion["arguments"]==example["expected"]["arguments"]})
        except Exception as exc:
            results.append({"valid":False,"tool_match":False,
                            "args_match":False,"error":type(exc).__name__})
    total=len(results)
    report={"count":total,"valid_rate":sum(x["valid"] for x in results)/total,
            "tool_accuracy":sum(x["tool_match"] for x in results)/total,
            "argument_accuracy":sum(x["args_match"] for x in results)/total,
            "samples":results}
    Path(args.report).write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k!="samples"},sort_keys=True))

if __name__=="__main__":
    main()
