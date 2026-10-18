"""
chip_models_bench.py - measures two REAL language models on the LinuxONE AI accelerator against the plain CPU, and checks
that the answers agree.

  python3 chip_models_bench.py                       # 5 repeats of the MiniLM run, 3 of the Granite run
  python3 chip_models_bench.py --reps 7 --texts 500

Needs: torch (with the "nnpa" device, as in the Jupyter image), transformers, and the two models already downloaded
(sentence-transformers/all-MiniLM-L6-v2 and ibm-granite/granite-4.0-350m). Takes a few minutes.

What it does, and why it is more convincing than one timing:
  * every run is repeated and the runs alternate chip / CPU / chip / CPU, so a busy moment on the shared server hits both
  * the first run of each is a warm-up and is not counted
  * MiniLM: embeds N descriptions on both devices, then compares the two sets of vectors (cosine similarity per text)
  * Granite: writes the same JSON answer for several reports on both devices (greedy decoding), then counts how many
    answers are word-for-word identical
Writes models/chip_models.json (the web app shows it in /api/benchmark under chip.language_models).
"""
import argparse
import json
import os
import statistics as st
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ap = argparse.ArgumentParser()
ap.add_argument("--reps", type=int, default=5)
ap.add_argument("--granite-reps", type=int, default=3)
ap.add_argument("--texts", type=int, default=1000)
ap.add_argument("--data", default=os.environ.get("DATA_DIR", os.path.join(HERE, "..", "data")))
ap.add_argument("--out", default=os.environ.get("MODEL_DIR", os.path.join(HERE, "models")))
ap.add_argument("--minilm", default="sentence-transformers/all-MiniLM-L6-v2")
ap.add_argument("--granite", default=os.environ.get("GRANITE_MODEL", "ibm-granite/granite-4.0-350m"))
ap.add_argument("--granite-tokens", type=int, default=60)
a = ap.parse_args()

CHIP = os.environ.get("CHIP_DEVICE", "nnpa")      # only changed in tests, where there is no accelerator
import numpy as np          # noqa: E402
import pandas as pd         # noqa: E402

result = {"measured_at": time.strftime("%Y-%m-%d %H:%M:%S"), "reps": a.reps, "granite_reps": a.granite_reps}
os.makedirs(a.out, exist_ok=True)
out_path = os.path.join(a.out, "chip_models.json")


def save():
    json.dump(result, open(out_path, "w"), indent=1)


try:
    import torch
    from transformers import AutoModel, AutoModelForCausalLM, AutoTokenizer
except Exception as e:
    result["error"] = f"torch / transformers not available: {type(e).__name__}: {e}"
    save(); print(result["error"]); sys.exit(1)

result["torch"] = torch.__version__
result["cpu_threads"] = os.cpu_count()
torch.set_num_threads(os.cpu_count() or 1)
try:
    x = torch.randn(64, 64).to(CHIP); _ = (x @ x).to("cpu")
    result["nnpa_available"] = True
except Exception as e:
    result["nnpa_available"] = False
    result["error"] = f"nnpa device not available: {type(e).__name__}: {str(e)[:200]}"
    save(); print(result["error"]); sys.exit(1)


def summarise(chip, cpu):
    r = lambda v: round(v, 3)
    return {"chip_seconds": [r(v) for v in chip], "cpu_seconds": [r(v) for v in cpu],
            "chip_median": r(st.median(chip)), "cpu_median": r(st.median(cpu)),
            "speedup_median": r(st.median(cpu) / st.median(chip)),
            "speedup_worst_pair": r(min(c / n for c, n in zip(cpu, chip))),
            "speedup_best_pair": r(max(c / n for c, n in zip(cpu, chip)))}


# ---------------------------------------------------------------------------------------- MiniLM
print("MiniLM ...", flush=True)
try:
    texts = []
    for n in ("missing.csv", "found.csv"):
        texts += list(pd.read_csv(os.path.join(a.data, n)).fillna("")["description"])
    texts = (texts * (a.texts // max(1, len(texts)) + 1))[:a.texts]
    tok = AutoTokenizer.from_pretrained(a.minilm)
    model = AutoModel.from_pretrained(a.minilm).eval()
    models = {"chip": model.to(CHIP), "cpu": AutoModel.from_pretrained(a.minilm).eval()}
    dev = {"chip": CHIP, "cpu": "cpu"}

    def embed(which):
        vecs, t0 = [], time.perf_counter()
        with torch.no_grad():
            for i in range(0, len(texts), 64):
                b = tok(texts[i:i + 64], padding=True, truncation=True, max_length=128, return_tensors="pt")
                b = {k: v.to(dev[which]) for k, v in b.items()}
                h = models[which](**b).last_hidden_state
                m = b["attention_mask"].unsqueeze(-1).to(h.dtype)
                v = torch.nn.functional.normalize((h * m).sum(1) / m.sum(1).clamp(min=1e-9), dim=-1)
                vecs.append(v.to("cpu").float().numpy())
        return np.vstack(vecs), time.perf_counter() - t0

    embed("chip"); embed("cpu")                                           # warm-up, not counted
    times, last = {"chip": [], "cpu": []}, {}
    for r in range(a.reps):
        for which in (("chip", "cpu") if r % 2 == 0 else ("cpu", "chip")):
            last[which], t = embed(which)
            times[which].append(t)
        print(f"  rep {r + 1}/{a.reps}: chip {times['chip'][-1]:.2f}s  cpu {times['cpu'][-1]:.2f}s", flush=True)
    cos = (last["chip"] * last["cpu"]).sum(1)
    result["minilm"] = {"model": a.minilm, "texts": len(texts), **summarise(times["chip"], times["cpu"]),
                        "output_agreement": {"cosine_similarity_min": round(float(cos.min()), 5),
                                             "cosine_similarity_mean": round(float(cos.mean()), 5),
                                             "max_abs_difference": round(float(np.abs(last["chip"] - last["cpu"]).max()), 5)}}
    print("  ", json.dumps(result["minilm"]))
    del models, model
except Exception as e:
    result["minilm"] = {"error": f"{type(e).__name__}: {str(e)[:300]}"}
    print("  MiniLM failed:", result["minilm"]["error"])
save()

# ---------------------------------------------------------------------------------------- Granite
print("Granite ...", flush=True)
try:
    from extract import PROMPT
    reports = []
    for n in ("missing.csv", "found.csv"):
        reports += list(pd.read_csv(os.path.join(a.data, n)).fillna("")["description"][:3])
    reports = reports[:5]
    gtok = AutoTokenizer.from_pretrained(a.granite)
    gtok.padding_side = "left"
    if gtok.pad_token is None:
        gtok.pad_token = gtok.eos_token
    def load_granite():
        try:
            return AutoModelForCausalLM.from_pretrained(a.granite, dtype=torch.float32).eval()
        except TypeError:                                                   # older transformers call it torch_dtype
            return AutoModelForCausalLM.from_pretrained(a.granite, torch_dtype=torch.float32).eval()
    gm = {"cpu": load_granite()}
    gm["chip"] = load_granite().to(CHIP)
    dev = {"chip": CHIP, "cpu": "cpu"}

    def generate(which, text):
        msg = gtok.apply_chat_template([{"role": "user", "content": PROMPT.replace("{report}", text)}],
                                       add_generation_prompt=True, tokenize=False)
        x = gtok([msg], return_tensors="pt", add_special_tokens=False).to(dev[which])
        t0 = time.perf_counter()
        with torch.no_grad():
            g = gm[which].generate(**x, max_new_tokens=a.granite_tokens, do_sample=False, pad_token_id=gtok.pad_token_id)
        return gtok.decode(g[0][x["input_ids"].shape[1]:], skip_special_tokens=True), time.perf_counter() - t0

    generate("chip", reports[0]); generate("cpu", reports[0])             # warm-up
    times, answers = {"chip": [], "cpu": []}, {"chip": [], "cpu": []}
    for r in range(a.granite_reps):
        for which in (("chip", "cpu") if r % 2 == 0 else ("cpu", "chip")):
            t_run = 0.0
            outs = []
            for text in reports:
                s, t = generate(which, text)
                outs.append(s); t_run += t
            times[which].append(t_run); answers[which] = outs
        print(f"  rep {r + 1}/{a.granite_reps}: chip {times['chip'][-1]:.1f}s  cpu {times['cpu'][-1]:.1f}s "
              f"(for {len(reports)} reports of up to {a.granite_tokens} new tokens)", flush=True)
    same = sum(c == p for c, p in zip(answers["chip"], answers["cpu"]))
    result["granite"] = {"model": a.granite, "reports_per_run": len(reports), "max_new_tokens": a.granite_tokens,
                         **summarise(times["chip"], times["cpu"]),
                         "identical_answers": f"{same} of {len(reports)}",
                         "example_chip_answer": answers["chip"][0][:200], "example_cpu_answer": answers["cpu"][0][:200]}
    print("  ", json.dumps({k: v for k, v in result["granite"].items() if not k.startswith("example")}))
except Exception as e:
    result["granite"] = {"error": f"{type(e).__name__}: {str(e)[:300]}"}
    print("  Granite failed:", result["granite"]["error"])
result["note"] = ("Real neural networks run through PyTorch on torch.device('nnpa') (the Telum on-chip accelerator) versus the "
                  "plain CPU, repeated and alternated. The server is shared, so absolute times move; compare the two columns.")
save()
print("written", out_path)
