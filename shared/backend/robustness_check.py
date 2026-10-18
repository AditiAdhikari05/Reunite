"""
robustness_check.py - how does the trained matcher do on a DIFFERENT synthetic dataset (new wording, more typos)?

  python3 robustness_check.py ../shared/data_hard            # Aneeza's harder dataset
  python3 robustness_check.py ../data                        # the dataset it was trained on, for comparison

Uses the models in models/ (trained on ../data) and the held-out TEST reports of the dataset you point at.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np   # noqa: E402
import pandas as pd  # noqa: E402
from engine import Engine  # noqa: E402

data = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "shared", "data_hard")
models = os.environ.get("MODEL_DIR", os.path.join(HERE, "models"))
eng = Engine(data, models, os.path.join(tempfile.mkdtemp(), "state.json"), backend="numpy", log=lambda *a: None)
m = pd.read_csv(os.path.join(data, "missing.csv"))
t = pd.read_csv(os.path.join(data, "truth.csv"))
true_of, test = dict(zip(t.missing_id, t.found_id)), set(m.loc[m.split == "test", "id"])
fpos = {f: j for j, f in enumerate(eng.fdf["id"])}
ranks = []
for i, mid in enumerate(eng.mdf["id"]):
    if mid in test and mid in true_of and true_of[mid] in fpos:
        row = eng.S[i]
        ranks.append(1 + int((row > row[fpos[true_of[mid]]]).sum()))
r = np.array(ranks)
print(f"{os.path.basename(os.path.normpath(data))}: {len(r)} held-out reports with a real match, {len(fpos)} found people searched")
print(f"  true match ranked 1st {(r <= 1).mean():.1%}   top 5 {(r <= 5).mean():.1%}   top 10 {(r <= 10).mean():.1%}   median rank {np.median(r):.0f}")
