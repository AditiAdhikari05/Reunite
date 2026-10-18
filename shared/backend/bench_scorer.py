"""
bench_scorer.py - measures our real match scorer with the accelerator ON, OFF, and in plain numpy.

Run:   python bench_scorer.py                 (about a minute)
       python bench_scorer.py --pairs 8000000  (bigger batch)
Writes models/benchmark_scorer.json, which the web app shows on /api/benchmark.

Each run happens in a separate process because NNPA_DEVICES must be set before TensorFlow starts.
The workload is the real feature matrix of every report vs every found person, repeated (tiled) up to
--pairs rows so the timing is stable. Tiling does not change how long scoring takes.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import features as FT  # noqa: E402
import train as T      # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(HERE, "..", "data"))
    ap.add_argument("--models", default=os.path.join(HERE, "models"))
    ap.add_argument("--weights", default=None, help="weights file, default models/scorer.npz")
    ap.add_argument("--pairs", type=int, default=2_000_000)
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--skip-tf", action="store_true", help="only time numpy (for testing the script)")
    a = ap.parse_args()
    weights = a.weights or os.path.join(a.models, "scorer.npz")

    missing, found, truth, places = T.load_dataset(a.data)
    art = FT.Artifacts(places).fit(missing, found)
    M, F = FT.build_side(missing, "missing", art), FT.build_side(found, "found", art)
    X = FT.pair_tensor(M, F).reshape(-1, len(FT.FEATURES))
    natural = len(X)
    X = np.tile(X, (int(np.ceil(a.pairs / natural)), 1))[:a.pairs].astype(np.float32)
    print(f"{natural} real pairs, tiled to {len(X)} rows")

    tmp = tempfile.mkdtemp()
    xp = os.path.join(tmp, "X.npy"); np.save(xp, X)
    plan = [("numpy_cpu", "numpy", {})]
    if not a.skip_tf:
        log = {"TF_CPP_MIN_LOG_LEVEL": "0", "TF_CPP_VMODULE": "remapper=1"}
        plan += [("accelerator_off", "tf", {"NNPA_DEVICES": "0", **log}), ("accelerator_on", "tf", dict(log))]
    runs, preds = {}, {}
    for tag, backend, env in plan:
        print("running", tag, "...", flush=True)
        pp = os.path.join(tmp, f"pred_{tag}.npy")
        e = {k: v for k, v in os.environ.items() if k != "NNPA_DEVICES"}
        e.update(env)
        p = subprocess.run([sys.executable, os.path.join(HERE, "bench_worker.py"), "--x", xp, "--weights", weights,
                            "--backend", backend, "--reps", str(a.reps), "--pred", pp, "--pred-rows", str(natural)],
                           env=e, capture_output=True, text=True)
        line = next((l for l in reversed(p.stdout.splitlines()) if l.startswith("{")), None)
        if p.returncode != 0 or line is None:
            runs[tag] = {"error": (p.stderr.strip().splitlines() or ["failed"])[-1][:300]}
            print("   FAILED:", runs[tag]["error"])
            continue
        runs[tag] = json.loads(line)
        runs[tag]["z_ops_remapped_in_log"] = p.stderr.count("remapping to Z op")
        preds[tag] = np.load(pp)
        print(f"   {runs[tag]['rows_per_sec']:,} pairs/s  ({runs[tag]['seconds']} s for {runs[tag]['rows']:,} pairs)  z-ops in log: {runs[tag]['z_ops_remapped_in_log']}")

    out = {"weights_file": os.path.basename(weights), "pairs_scored": int(len(X)), "real_pairs_before_tiling": int(natural), **runs}
    z = np.load(weights)
    out["layers"] = [list(z[f"W{i}"].shape) for i in range(int(z["n_layers"]))]
    on, off = runs.get("accelerator_on", {}), runs.get("accelerator_off", {})
    if "rows_per_sec" in on and "rows_per_sec" in off:
        out["chip_on"] = {"pairs_per_sec": on["rows_per_sec"], "seconds": on["seconds"]}
        out["chip_off"] = {"pairs_per_sec": off["rows_per_sec"], "seconds": off["seconds"]}
        sp = on["rows_per_sec"] / off["rows_per_sec"]
        out["speedup_on_vs_off"] = round(sp, 2)
        nm, nf = len(missing), len(found)
        ref = preds["numpy_cpu"]
        out["parity"] = {"max_abs_score_difference_on_vs_numpy": float(np.abs(preds["accelerator_on"] - ref).max()),
                         "top1_same_as_numpy_for_share_of_reports": float((preds["accelerator_on"].reshape(nm, nf).argmax(1) == ref.reshape(nm, nf).argmax(1)).mean())}
        n_layers = len(out["layers"])
        if sp >= 1.5:
            out["interpretation"] = f"With the accelerator the scorer is {sp:.1f}x faster on this batch."
        elif sp >= 0.8:
            out["interpretation"] = (f"No meaningful speed-up ({sp:.2f}x). This scorer has {n_layers} layer(s) and {out['layers'][0][0]} inputs, "
                                     "which is too small for the accelerator to help. Larger neural networks do benefit (see the stress test).")
        else:
            out["interpretation"] = (f"The accelerator was slower ({sp:.2f}x) for this tiny model: moving data to the accelerator costs more than the maths saves.")
    json.dump(out, open(os.path.join(a.models, "benchmark_scorer.json" if a.weights is None else f"benchmark_{os.path.basename(weights)[:-4]}.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in out.items() if k in ("speedup_on_vs_off", "interpretation", "parity")}, indent=1))


if __name__ == "__main__":
    main()
