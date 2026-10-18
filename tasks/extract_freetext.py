"""Task 2: pull hair, clothing and marks out of the free-text description with Granite, plus a regex fallback.
Scores each extractor per field against the structured columns.

  python extract_freetext.py --backend regex                 # fast, no model
  python extract_freetext.py --backend granite --n 200        # Granite (GPU on Colab is much faster than CPU)
  python extract_freetext.py --backend granite --data shared/data_hard   # same test on the harder dataset

Writes results/extract_<backend>_<dataset>.json (metrics) and .csv (every prediction).
Three numbers per field: Granite alone, regex alone, Granite with regex fallback.
"""
import argparse, json, os, re, time
import numpy as np
import pandas as pd
import make_data as md
import vocab_canon as vc

ap = argparse.ArgumentParser()
ap.add_argument("--backend", choices=["regex", "granite"], default="regex")
ap.add_argument("--data", default=os.path.join("shared", "data"))
ap.add_argument("--n", type=int, default=0, help="records to test (0 = all). Granite on CPU: keep small")
ap.add_argument("--model", default="ibm-granite/granite-4.0-350m")
ap.add_argument("--batch", type=int, default=16)
a = ap.parse_args()

# The regex fallback only knows the ORIGINAL vocabulary (like a hand-written normaliser would).
# Scoring must understand the dataset's own vocabulary, which differs for the hard dataset.
REGEX = vc.ORIGINAL
if "hard" in os.path.basename(os.path.normpath(a.data)):
    import make_data_hard  # noqa: F401  (patches make_data's vocabulary in place)
GOLD = vc.Canon.from_module(md)

rows = pd.concat([pd.read_csv(os.path.join(a.data, "missing.csv")).assign(kind="missing"),
                  pd.read_csv(os.path.join(a.data, "found.csv")).assign(kind="found")]).fillna("")
if a.n:
    rows = rows.sample(a.n, random_state=0)
rows = rows.reset_index(drop=True)

# ------------------------------------------------------------------ Granite
PROMPT = """Extract the person's hair, clothing and distinguishing marks from the report.
Return only JSON: {"hair": string or null, "clothing": [list of items], "marks": [list of marks]}.
Copy the words from the report. Use null or [] if the report does not mention it.

Report: Elderly woman, approx. 70-75, found at Old Grain Market, wearing navy coat, grey slacks. Hair: short silver. Mole on left cheek.
JSON: {"hair": "short silver", "clothing": ["navy coat", "grey slacks"], "marks": ["mole on left cheek"]}

Report: My brother, 31, was last seen near Ferry Bridge. Please help.
JSON: {"hair": null, "clothing": [], "marks": []}

Report: {report}
JSON:"""

def granite_extract(texts):
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
    dev = os.environ.get("DEVICE") or ("cuda" if torch.cuda.is_available() else "cpu")
    torch.set_num_threads(os.cpu_count() or 1)
    tok = AutoTokenizer.from_pretrained(a.model); tok.padding_side = "left"
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    try:
        model = AutoModelForCausalLM.from_pretrained(a.model, dtype=torch.float16 if dev == "cuda" else torch.float32).to(dev).eval()
    except TypeError:
        model = AutoModelForCausalLM.from_pretrained(a.model, torch_dtype=torch.float16 if dev == "cuda" else torch.float32).to(dev).eval()
    print("Granite on", dev)
    out, raw = [], []
    t0 = time.time()
    for i in range(0, len(texts), a.batch):
        chunk = texts[i:i + a.batch]
        msgs = [tok.apply_chat_template([{"role": "user", "content": PROMPT.replace("{report}", t)}], add_generation_prompt=True, tokenize=False) for t in chunk]
        x = tok(msgs, return_tensors="pt", padding=True, add_special_tokens=False).to(dev)
        with torch.no_grad():
            g = model.generate(**x, max_new_tokens=120, do_sample=False, pad_token_id=tok.pad_token_id)
        for o in g:
            s = tok.decode(o[x["input_ids"].shape[1]:], skip_special_tokens=True)
            raw.append(s); out.append(parse(s))
        print(f"{min(i + a.batch, len(texts))}/{len(texts)}  {(time.time() - t0) / min(i + a.batch, len(texts)):.2f}s per report", flush=True)
    return out, raw, (time.time() - t0) / len(texts)

def parse(s):
    m = re.search(r"\{.*?\}", s, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    lst = lambda v: [str(x) for x in v] if isinstance(v, list) else ([str(v)] if v else [])
    return {"hair": d.get("hair") if isinstance(d.get("hair"), str) else None, "clothing": lst(d.get("clothing")), "marks": lst(d.get("marks"))}

def with_fallback(g, r):
    """Use Granite, fill anything it missed (or failed to parse) from the regex extractor."""
    if g is None:
        return r
    return {"hair": g["hair"] or r["hair"], "clothing": g["clothing"] or r["clothing"], "marks": g["marks"] or r["marks"]}

# ------------------------------------------------------------------ run + score
regex_preds = [REGEX.regex_extract(d) for d in rows["description"]]
systems = {"regex": regex_preds}
secs = None
if a.backend == "granite":
    g, raw, secs = granite_extract(list(rows["description"]))
    systems["granite"] = [p or {"hair": None, "clothing": [], "marks": []} for p in g]
    systems["granite+regex_fallback"] = [with_fallback(p, r) for p, r in zip(g, regex_preds)]
    valid_json = sum(p is not None for p in g) / len(g)

mentions = {
    "clothing": rows["description"].map(lambda d: bool(GOLD.RE_GARMENT.search(d))),
    "hair": rows["description"].map(lambda d: bool(re.search(r"\bhair\b|\bbald\b", d, re.I))),
}
res = {"dataset": a.data, "records": len(rows)}
if a.backend == "granite":
    res.update(valid_json=round(valid_json, 3), seconds_per_report=round(secs, 3))
for name, preds in systems.items():
    sc = pd.DataFrame([GOLD.score(p, r) for p, r in zip(preds, rows.to_dict("records"))])
    res[name] = {k: round(float(sc[k].mean()), 3) for k in sc}
    res[name]["clothing_f1_when_text_mentions_clothing"] = round(float(sc.loc[mentions["clothing"], "clothing_f1"].mean()), 3)
    res[name]["hair_color_when_text_mentions_hair"] = round(float(sc.loc[mentions["hair"], "hair_color"].mean()), 3)
    rows[f"pred_{name}"] = [json.dumps(p, ensure_ascii=False) for p in preds]

os.makedirs("results", exist_ok=True)
tag = f"{a.backend}_{os.path.basename(os.path.normpath(a.data))}"
json.dump(res, open(f"results/extract_{tag}.json", "w"), indent=2)
rows.to_csv(f"results/extract_{tag}.csv", index=False)
print(json.dumps(res, indent=2))
