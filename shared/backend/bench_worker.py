"""bench_worker.py - one timing run in its own process (so NNPA_DEVICES is read before TensorFlow starts). Used by bench_scorer.py."""
import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scorer import NumpyMLP, TfMLP, device_mode  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--x"); ap.add_argument("--weights"); ap.add_argument("--backend", choices=["numpy", "tf"])
ap.add_argument("--reps", type=int, default=5); ap.add_argument("--pred"); ap.add_argument("--pred-rows", type=int, default=240000)
a = ap.parse_args()
X = np.load(a.x)
z = np.load(a.weights)
layers = [(z[f"W{i}"], z[f"b{i}"]) for i in range(int(z["n_layers"]))]
model = TfMLP(layers) if a.backend == "tf" else NumpyMLP(layers)
out = model.predict(X[:20000])                       # warm-up
times = []
for _ in range(a.reps):
    t = time.time(); out = model.predict(X); times.append(time.time() - t)
np.save(a.pred, out[:a.pred_rows])
med = float(np.median(times))
print(json.dumps({"rows": int(len(X)), "seconds": round(med, 4), "rows_per_sec": int(len(X) / med),
                  "all_runs_seconds": [round(t, 4) for t in times], "mode": device_mode(a.backend == "tf"),
                  "nnpa_devices_env": os.environ.get("NNPA_DEVICES")}))
