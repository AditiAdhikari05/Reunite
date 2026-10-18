"""Model 1: fine-tune Granite 350M (LoRA) to turn a report in any language into the Reunite JSON.
CPU-friendly for a 3-core LinuxONE server: small balanced sample, short sequences, checkpoints as it goes.

Run in the background so it survives the notebook:
  nohup python finetune_granite.py --limit 1200 > finetune.log 2>&1 &
  tail -f finetune.log
Stop any time: the latest checkpoint is in models/granite_lora and can be evaluated.
"""
import argparse, json, os, random, time
import torch
from llm_common import load_model, split_rows, prompt_text, ADAPTER_DIR

ap = argparse.ArgumentParser()
ap.add_argument("--limit", type=int, default=1200, help="training examples (balanced across languages)")
ap.add_argument("--epochs", type=int, default=1)
ap.add_argument("--max_len", type=int, default=384)
ap.add_argument("--lr", type=float, default=2e-4)
ap.add_argument("--accum", type=int, default=8)
ap.add_argument("--rank", type=int, default=16)
ap.add_argument("--save_every", type=int, default=25, help="optimizer steps between checkpoints")
a = ap.parse_args()

random.seed(0); torch.manual_seed(0)
rows = split_rows("train")
by_lang = {}
for r in rows:
    by_lang.setdefault(r["language"], []).append(r)
per = max(1, a.limit // len(by_lang))
data = [r for L in by_lang.values() for r in random.sample(L, min(per, len(L)))]
random.shuffle(data)
print(f"{len(data)} training examples across {len(by_lang)} languages")

tok, model = load_model()
from peft import LoraConfig, get_peft_model
model = get_peft_model(model, LoraConfig(r=a.rank, lora_alpha=2 * a.rank, lora_dropout=0.05, target_modules="all-linear", task_type="CAUSAL_LM"))
model.print_trainable_parameters()
model.train()

def encode(r):
    p = prompt_text(tok, r["input"])
    target = json.dumps(r["output"], ensure_ascii=False) + (tok.eos_token or "")
    pi = tok(p, add_special_tokens=False)["input_ids"]
    ti = tok(target, add_special_tokens=False)["input_ids"]
    if len(pi) + len(ti) > a.max_len:
        return None, None
    return torch.tensor([pi + ti]), torch.tensor([[-100] * len(pi) + ti])

opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=a.lr)
total = len(data) * a.epochs // a.accum
step, t0, run_loss = 0, time.time(), []
for ep in range(a.epochs):
    for i, r in enumerate(data):
        ids, labels = encode(r)
        if ids is None:
            continue
        loss = model(input_ids=ids, labels=labels).loss / a.accum
        if not torch.isfinite(loss):
            print("  skipped one unstable example", flush=True); continue
        loss.backward(); run_loss.append(loss.item() * a.accum)
        if (i + 1) % a.accum == 0:
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step(); opt.zero_grad(); step += 1
            el = time.time() - t0
            print(f"step {step}/{total}  loss {sum(run_loss[-a.accum*5:])/len(run_loss[-a.accum*5:]):.3f}  "
                  f"elapsed {el/60:.1f} min  eta {el/step*(total-step)/60:.0f} min", flush=True)
            if step % a.save_every == 0:
                model.save_pretrained(ADAPTER_DIR); print(f"  checkpoint saved -> {ADAPTER_DIR}", flush=True)
model.save_pretrained(ADAPTER_DIR)
json.dump({"examples": len(data), "steps": step, "minutes": round((time.time() - t0) / 60, 1), "final_loss": round(sum(run_loss[-50:]) / len(run_loss[-50:]), 3)},
          open(os.path.join(ADAPTER_DIR, "train_info.json"), "w"), indent=2)
print("done, adapter saved to", ADAPTER_DIR)
