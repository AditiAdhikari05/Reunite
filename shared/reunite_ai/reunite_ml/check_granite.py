"""Step 1 on the server: can we download and run Granite 350M on LinuxONE?
Tries the Granite 4.0 350M variants in order, runs one Arabic report (a language from the unseen test country),
and saves the model name that worked. Run:  python check_granite.py
"""
import time, json
from llm_common import CANDIDATES, MODEL_FILE, load_model, extract, split_rows

sample = next(r for r in split_rows("test") if r["language"] == "ar")
for mid in CANDIDATES:
    try:
        t = time.time()
        tok, model = load_model(mid)
        n = sum(p.numel() for p in model.parameters())
        print(f"loaded {mid}: {n/1e6:.0f}M parameters in {time.time()-t:.0f}s")
        t = time.time()
        obj, raw = extract(tok, model, sample["input"])
        print(f"one report took {time.time()-t:.1f}s")
        print("REPORT:", sample["input"])
        print("MODEL SAID:", raw[:600])
        print("PARSED OK:", obj is not None)
        print("CORRECT ANSWER:", json.dumps(sample["output"], ensure_ascii=False))
        open(MODEL_FILE, "w").write(mid)
        print(f"\nsaved model choice -> {MODEL_FILE}. Before fine-tuning, the answer is usually wrong or messy. That's expected.")
        break
    except Exception as e:
        print(f"{mid} failed: {type(e).__name__}: {str(e)[:300]}")
