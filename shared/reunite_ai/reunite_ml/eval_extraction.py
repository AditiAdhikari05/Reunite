"""Measure how well Granite reads reports, before and after fine-tuning, on countries it never trained on.
  python eval_extraction.py --n 100 --base        # Granite as downloaded (no fine-tuning)
  python eval_extraction.py --n 100               # Granite + our fine-tuned adapter
Writes models/extraction_metrics_<base|tuned>.json, and models/extracted.jsonl (the model's own answers),
which the matcher then uses instead of the gold labels: that makes the whole pipeline end to end.
"""
import argparse, json, os, random, time
from collections import defaultdict
from common import MODELS, name_tokens
from llm_common import load_model, extract, split_rows, ADAPTER_DIR

ap = argparse.ArgumentParser()
ap.add_argument("--n", type=int, default=100)
ap.add_argument("--split", default="test")
ap.add_argument("--base", action="store_true", help="evaluate without the fine-tuned adapter")
a = ap.parse_args()

random.seed(1)
rows = split_rows(a.split)
by_lang = defaultdict(list)
for r in rows:
    by_lang[r["language"]].append(r)
per = max(1, a.n // len(by_lang))
sample = [r for L in by_lang.values() for r in random.sample(L, min(per, len(L)))]
tok, model = load_model(adapter=None if a.base else ADAPTER_DIR)

def same(field, p, g):
    if field in ("clothing", "marks", "medical", "languages"):
        return set(map(str.lower, p or [])) == set(map(str.lower, g or []))
    if field == "name_latin":
        return name_tokens(p) == name_tokens(g) if (p and g) else p == g
    if isinstance(g, str) and isinstance(p, str):
        return p.strip().lower() == g.strip().lower()
    return p == g

fields = list(sample[0]["output"])
ok = defaultdict(int); valid = 0; allok = 0; per_lang = defaultdict(lambda: [0, 0]); t0 = time.time()
out_path = os.path.join(MODELS, "extracted.jsonl")
with open(out_path, "a", encoding="utf-8") as fo:
    for i, r in enumerate(sample):
        pred, raw = extract(tok, model, r["input"])
        g = r["output"]
        if pred:
            valid += 1
            right = [f for f in fields if same(f, pred.get(f), g[f])]
            for f in right: ok[f] += 1
            allok += len(right) == len(fields)
            per_lang[r["language"]][0] += len(right) / len(fields)
            if not a.base:
                fo.write(json.dumps({"id": r["id"], "output": pred}, ensure_ascii=False) + "\n")
        per_lang[r["language"]][1] += 1
        if (i + 1) % 10 == 0:
            print(f"{i+1}/{len(sample)}  {(time.time()-t0)/(i+1):.1f}s per report", flush=True)

n = len(sample)
res = {"model": "base" if a.base else "fine-tuned", "split": a.split, "reports": n, "valid_json": round(valid / n, 3),
       "all_fields_correct": round(allok / n, 3), "field_accuracy": {f: round(ok[f] / n, 3) for f in fields},
       "by_language": {k: round(v[0] / v[1], 3) for k, v in per_lang.items()}, "seconds_per_report": round((time.time() - t0) / n, 2)}
print(json.dumps(res, indent=2, ensure_ascii=False))
json.dump(res, open(os.path.join(MODELS, f"extraction_metrics_{'base' if a.base else 'tuned'}.json"), "w"), indent=2)
