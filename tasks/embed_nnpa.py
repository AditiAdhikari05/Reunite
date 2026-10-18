"""Task 1: run a small sentence-embedding model (MiniLM) on LinuxONE's AI accelerator.
Tries torch.device("nnpa") first and falls back to CPU, recording exactly what happened (that's the evidence).
Then checks whether text similarity helps matching, especially when the structured fields are blank.

  python embed_nnpa.py                     # tries nnpa, then also runs CPU for a timing comparison
  python embed_nnpa.py --devices cpu       # CPU only (e.g. on Colab or a laptop)

Writes results/embeddings_<device>.npz, results/embed_timing.json, results/embed_matching.json
"""
import argparse, json, os, time, traceback
import numpy as np
import pandas as pd
import torch

ap = argparse.ArgumentParser()
ap.add_argument("--data", default=os.path.join("shared", "data"))
ap.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2")
ap.add_argument("--devices", default="nnpa,cpu")
ap.add_argument("--batch", type=int, default=64)
a = ap.parse_args()
torch.set_num_threads(os.cpu_count() or 1)
os.makedirs("results", exist_ok=True)

from transformers import AutoTokenizer, AutoModel
tok = AutoTokenizer.from_pretrained(a.model)
M = pd.read_csv(os.path.join(a.data, "missing.csv")).fillna("")
F = pd.read_csv(os.path.join(a.data, "found.csv")).fillna("")
T = pd.read_csv(os.path.join(a.data, "truth.csv"))
texts = list(M["description"]) + list(F["description"])

def device_works(name):
    """Small smoke test so we know the device really runs a matrix multiply."""
    try:
        d = torch.device(name)
        x = torch.randn(64, 64).to(d)
        y = (x @ x).to("cpu")
        return True, f"matmul on {name} ok, checksum {float(y.sum()):.2f}"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:300]}"

def embed(device):
    model = AutoModel.from_pretrained(a.model).eval().to(device)
    vecs, t0 = [], time.perf_counter()
    with torch.no_grad():
        for i in range(0, len(texts), a.batch):
            x = tok(texts[i:i + a.batch], padding=True, truncation=True, max_length=128, return_tensors="pt")
            x = {k: v.to(device) for k, v in x.items()}
            h = model(**x).last_hidden_state
            m = x["attention_mask"].unsqueeze(-1).to(h.dtype)
            v = (h * m).sum(1) / m.sum(1).clamp(min=1e-9)            # mean pooling
            v = torch.nn.functional.normalize(v, dim=-1)
            vecs.append(v.to("cpu").float().numpy())
    secs = time.perf_counter() - t0
    return np.vstack(vecs), secs

timing = {"model": a.model, "texts": len(texts), "torch": torch.__version__, "runs": {}}
emb = None
for name in [d.strip() for d in a.devices.split(",") if d.strip()]:
    ok, note = device_works(name)
    print(f"[{name}] device check: {note}")
    if not ok:
        timing["runs"][name] = {"works": False, "error": note}
        continue
    try:
        E, secs = embed(torch.device(name))
        np.savez_compressed(f"results/embeddings_{name}.npz", ids=np.array(list(M["id"]) + list(F["id"])), emb=E)
        timing["runs"][name] = {"works": True, "check": note, "seconds_total": round(secs, 3), "ms_per_text": round(1000 * secs / len(texts), 2)}
        print(f"[{name}] embedded {len(texts)} texts in {secs:.2f}s ({1000*secs/len(texts):.1f} ms each)")
        emb = E if emb is None else emb
    except Exception as e:
        timing["runs"][name] = {"works": False, "error": f"{type(e).__name__}: {str(e)[:300]}", "trace": traceback.format_exc()[-800:]}
        print(f"[{name}] embedding failed: {type(e).__name__}: {str(e)[:200]}")
if all(r.get("works") for r in timing["runs"].values()) and len(timing["runs"]) == 2:
    r = list(timing["runs"].values()); timing["speedup_first_vs_second"] = round(r[1]["seconds_total"] / r[0]["seconds_total"], 2)
json.dump(timing, open("results/embed_timing.json", "w"), indent=2)

# ------------------------------------------------------------------ does text similarity help matching?
if emb is not None:
    Em, Ef = emb[:len(M)], emb[len(M):]
    sim = Em @ Ef.T                                                # cosine similarity (vectors are normalised)
    fidx = {f: i for i, f in enumerate(F["id"])}
    true = dict(zip(T["missing_id"], T["found_id"]))
    sparse = ((M["hair"] == "").astype(int) + (M["marks"] == "").astype(int) + (M["height_cm"] == "").astype(int)) >= 2
    def recall(mask):
        hits1 = hits5 = n = 0
        for i, mid in enumerate(M["id"]):
            if not mask[i] or mid not in true:
                continue
            order = np.argsort(-sim[i]); rank = int(np.where(order == fidx[true[mid]])[0][0])
            n += 1; hits1 += rank == 0; hits5 += rank < 5
        return {"reports": n, "top1": round(hits1 / max(n, 1), 3), "top5": round(hits5 / max(n, 1), 3)}
    res = {"text_similarity_only_all_reports": recall(np.ones(len(M), bool)),
           "text_similarity_only_sparse_reports": recall(sparse.values),
           "note": "Sparse = at least 2 of hair, marks, height blank. Add the similarity as one more feature in the matcher and keep it only if test recall improves."}
    json.dump(res, open("results/embed_matching.json", "w"), indent=2)
    print(json.dumps(res, indent=2))
print(json.dumps({k: v for k, v in timing.items() if k != "runs"} | {"runs": {k: {kk: vv for kk, vv in v.items() if kk != "trace"} for k, v in timing["runs"].items()}}, indent=2))
