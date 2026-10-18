"""Model 2: the matcher. Learns whether a missing report and a found report describe the same person.
Trains on 8 countries, tests on 2 countries it has never seen (Morocco, Philippines).
Run:  python train_matcher.py
"""
import json, time, random, os
import numpy as np
from common import (missing_records, found_records, truth, candidates, pair_features, FEATURES, make_classifier, proba, save, split_of, MODELS)

t0 = time.time()
random.seed(0)
T = truth()
M, F = missing_records(), found_records()
by_country = {}
for f in F:
    by_country.setdefault(f["country"], []).append(f)
print(f"{len(M)} missing reports, {len(F)} found reports")

# --- build candidate pairs (blocking), so the model compares ~40 likely candidates instead of everyone
rows = {"train": [], "test": []}
blocked = kept = 0
for m in M:
    pool = by_country[m["country"]]
    true_ids = {f["id"] for f in pool if T[f["id"]] == T[m["id"]]}
    cands = candidates(m, pool)
    if true_ids:
        blocked += 1
        kept += bool(true_ids & {c["id"] for c in cands})
    sp = "test" if split_of(m["country"]) == "test" else "train"
    for f in cands:
        rows[sp].append((m["id"], f["id"], pair_features(m, f), int(f["id"] in true_ids)))
print(f"candidate step keeps the true match for {kept}/{blocked} reports ({kept/blocked:.1%})")

Xtr = np.array([r[2] for r in rows["train"]], dtype="float32"); ytr = np.array([r[3] for r in rows["train"]])
print(f"training pairs: {len(ytr)} ({ytr.sum()} true matches)")
model, kind = make_classifier()
model.fit(Xtr, ytr)
print(f"trained {kind} in {time.time()-t0:.0f}s")

# --- evaluate on unseen countries
def rank_eval(pairs):
    by_m = {}
    for mid, fid, x, y in pairs:
        by_m.setdefault(mid, []).append((fid, x, y))
    top1 = top5 = n = 0
    for mid, lst in by_m.items():
        if not any(y for _, _, y in lst):
            continue
        p = proba(model, [x for _, x, _ in lst])
        order = np.argsort(-p)
        ys = [lst[i][2] for i in order]
        n += 1; top1 += ys[0] == 1; top5 += any(ys[:5])
    return top1, top5, n

test_m = [m for m in M if split_of(m["country"]) == "test"]
t1, t5, n = rank_eval(rows["test"])
n_all = sum(1 for m in test_m if any(T[f["id"]] == T[m["id"]] for f in by_country[m["country"]]))

# baseline: search by the name exactly as typed
b5 = 0
for m in test_m:
    pool = by_country[m["country"]]
    true_ids = {f["id"] for f in pool if T[f["id"]] == T[m["id"]]}
    if not true_ids:
        continue
    sc = sorted(((len(m["raw_t"] & f["raw_t"]), f["id"]) for f in pool), reverse=True)
    b5 += bool(true_ids & {fid for s, fid in sc[:5] if s > 0})

# false alarms: reports with no true match whose best score is still high
fa = nm = 0
by_m = {}
for mid, fid, x, y in rows["test"]:
    by_m.setdefault(mid, []).append((x, y))
for mid, lst in by_m.items():
    if any(y for _, y in lst):
        continue
    nm += 1; fa += proba(model, [x for x, _ in lst]).max() > 0.5

res = {"model": kind, "test_countries": ["MA", "PH"], "reports_with_true_match": n_all,
       "top1": round(t1 / n_all, 3), "top5": round(t5 / n_all, 3), "baseline_name_search_top5": round(b5 / n_all, 3),
       "false_alarm_rate": round(fa / max(nm, 1), 3), "features": FEATURES, "train_seconds": round(time.time() - t0)}
print(json.dumps(res, indent=2))
save({"model": model, "features": FEATURES, "kind": kind}, "matcher.pkl")
json.dump(res, open(os.path.join(MODELS, "matcher_metrics.json"), "w"), indent=2)
print("saved models/matcher.pkl")
