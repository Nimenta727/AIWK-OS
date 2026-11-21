"""Optional OFFLINE LoRA adapter training. Never train on the host.

Dry-run only validates data. Actual training requires a dedicated AIWS guest VM,
local model checkpoint and explicit user approval, and can require substantial
guest RAM/CPU (not constrained to the 3-5GB inference VRAM target).
"""
import argparse
import json
import os
from pathlib import Path
import sys

here=Path(__file__).resolve().parent
sys.path.insert(0,str(here))
sys.path.insert(0,str(here.parents[1]/"runtime"))
from validate_dataset import load_validate, check_independence
from aiws_local_model import LocalPlanner, system_prompt

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--dataset",default=str(here/"synthetic_intents_v2.jsonl"))
    parser.add_argument("--train-in-guest",action="store_true")
    parser.add_argument("--ack-large-guest-memory-cost",action="store_true")
    parser.add_argument("--epochs",type=int,default=1)
    args=parser.parse_args()
    if not args.train_in_guest:
        # Static CI dry run only; never read a user-specified host dataset.
        if Path(args.dataset).resolve() not in {(here/"synthetic_intents.jsonl").resolve(),
                                                (here/"synthetic_intents_v2.jsonl").resolve()}:
            parser.error("Non-guest dry runs may only validate bundled synthetic examples")
        rows,holdout=load_validate(args.dataset)
        check_independence(rows,holdout)
        print(json.dumps({"dry_run":True,"train_examples":len(rows),
                          "held_out":len(holdout),"adapter_trained":False}))
        return
    from aiws_guest_boundary import require_guest_runtime, protect_guest_workspace
    require_guest_runtime()
    if not args.ack_large_guest_memory_cost:
        parser.error("LoRA training requires explicit guest-only resource approval")
    if not 1<=args.epochs<=3:
        parser.error("Epochs must be between 1 and 3")
    dataset_path = Path(args.dataset).resolve(strict=True)
    # Production/authorized data is readable only from the dedicated guest
    # AIWS training directory. The bundled synthetic fixture is never used
    # as a real training source.
    training_root = (Path.home()/".local/share/aiws/training").resolve()
    if not dataset_path.is_relative_to(training_root):
        parser.error("Training dataset must reside inside private AIWS guest training directory")
    protect_guest_workspace(training_root, dataset_path)
    rows,holdout=load_validate(dataset_path)
    # Training data must never overlap the locked held-out sets (exact or near-duplicate).
    check_independence(rows,holdout)
    # Do not allow model training to load from or write to host/shared filesystems.
    state=Path.home()/".local/share/aiws"
    if state.is_symlink():
        parser.error("AIWS guest state path cannot be a symlink")
    state.mkdir(parents=True,mode=0o700,exist_ok=True)
    protect_guest_workspace(state.resolve())
    model_dir=state/"models/base"
    output=state/"adapters/local-intent-lora"
    if model_dir.is_symlink() or not model_dir.is_dir():
        parser.error("Locally provisioned original model directory missing")
    if output.is_symlink():
        parser.error("Adapter output may not be a symlink")
    protect_guest_workspace(state.resolve(),model_dir.resolve())
    # Prevent external model hub and training metric uploads.
    os.environ["HF_HUB_OFFLINE"]="1"
    os.environ["TRANSFORMERS_OFFLINE"]="1"
    os.environ["HF_DATASETS_OFFLINE"]="1"
    os.environ["WANDB_DISABLED"]="true"
    # CPU-only: even an available host GPU is never requested/passed through.
    os.environ["CUDA_VISIBLE_DEVICES"]=""
    try:
        from datasets import Dataset
        from peft import LoraConfig
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from trl import SFTConfig, SFTTrainer
    except ImportError as exc:
        parser.error("Optional guest-only transformers, datasets, trl and peft packages required: "+str(exc))
    tokenizer=AutoTokenizer.from_pretrained(str(model_dir),local_files_only=True)
    base=AutoModelForCausalLM.from_pretrained(str(model_dir),local_files_only=True)
    records=[]
    policy=system_prompt()   # identical to the production inference prompt
    for entry in rows.values():
        messages=[
            {"role":"system","content":policy},
            {"role":"user","content":entry["instruction"]},
            {"role":"assistant","content":json.dumps(
                LocalPlanner.canonical(entry["expected"]),ensure_ascii=False)}
        ]
        records.append({"text":tokenizer.apply_chat_template(
            messages,tokenize=False,add_generation_prompt=False)})
    dataset=Dataset.from_list(records)
    # This deliberately uses conservative CPU settings. Real hyperparameters
    # and model architecture compatibility must be benchmarked in the guest.
    config=SFTConfig(output_dir=str(output),num_train_epochs=args.epochs,
        per_device_train_batch_size=1,gradient_accumulation_steps=4,
        learning_rate=0.0001,max_length=1024,logging_steps=10,
        save_strategy="epoch",report_to=[],dataset_text_field="text",
        fp16=False,bf16=False)
    peft=LoraConfig(r=8,lora_alpha=16,lora_dropout=0.05,
                    target_modules="all-linear",bias="none",task_type="CAUSAL_LM")
    trainer=SFTTrainer(model=base,processing_class=tokenizer,
        args=config,train_dataset=dataset,peft_config=peft)
    trainer.train()
    output.mkdir(parents=True,exist_ok=True)
    trainer.save_model(str(output))
    tokenizer.save_pretrained(str(output))
    print(json.dumps({"adapter_trained":True,"path":str(output),
                      "guest_only":True,"cloud_used":False}))

if __name__=="__main__":
    main()
