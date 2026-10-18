"""Model 4: who is most at risk if not found soon?
Predicts the chance that a missing person is found in a critical condition (critical, unconscious or deceased),
from what the family report says plus how long they have been missing. Responders check the riskiest cases first.
Run:  python train_risk.py
"""
import json, os, time
import numpy as np
from common import missing_records, load_csv, truth, meta, ts, make_classifier, proba, save, split_of, MODELS

t0 = time.time()
T, META = truth(), meta()
HAZ = ["flood", "flash flood", "hurricane", "earthquake", "typhoon"]
MEDS = ["diabetes", "dementia", "heart condition", "asthma", "pregnant", "epilepsy"]
FEATS = ["age", "age_under5", "age_70plus", "gender_f", "hours_missing", "slow_mobility"] + [f"med_{m}" for m in MEDS] + [f"hazard_{h}" for h in HAZ]

outcome = {}  # person -> (bad outcome, found time)
for r in sorted(load_csv("found_reports.csv"), key=lambda r: r["found_at"]):
    pid = T[r["found_id"]]
    if pid not in outcome:
        outcome[pid] = (int(r["condition"] in ("critical", "unconscious", "deceased")), ts(r["found_at"]))

def features(m, hours):
    x = m["x"]
    age = ((x["age_min"] + x["age_max"]) / 2) if x.get("age_min") is not None else -1
    meds = set(x.get("medical") or [])
    slow = int(bool(set(x.get("marks") or []) & {"walks with a limp", "uses a walking stick"}))
    hz = META["scenarios"][m["country"]]["hazard"]
    return [age, int(0 <= age < 5), int(age >= 70), int(x.get("gender") == "F"), hours, slow] + [int(k in meds) for k in MEDS] + [int(hz == h) for h in HAZ]

if __name__ == "__main__":
    data = {"train": [], "test": []}
    seen = set()
    for m in sorted(missing_records(), key=lambda m: m["t"]):
        pid = T[m["id"]]
        if pid not in outcome or pid in seen:
            continue
        seen.add(pid)
        bad, found_t = outcome[pid]
        data["test" if split_of(m["country"]) == "test" else "train"].append((features(m, found_t - m["t"]), bad, m))

    Xtr = np.array([x for x, _, _ in data["train"]], dtype="float32"); ytr = np.array([y for _, y, _ in data["train"]])
    model, kind = make_classifier(small=True)
    model.fit(Xtr, ytr)

    Xte = np.array([x for x, _, _ in data["test"]], dtype="float32"); yte = np.array([y for _, y, _ in data["test"]])
    p = proba(model, Xte)
    from sklearn.metrics import roc_auc_score
    k = max(1, int(.2 * len(p)))
    top = np.argsort(-p)[:k]
    # simple rule baseline: elderly or has a medical condition
    rule = np.array([int(x[2] or sum(x[6:12]) > 0) for x, _, _ in data["test"]])
    res = {"model": kind, "test_countries": ["MA", "PH"], "cases": int(len(yte)), "base_rate_bad_outcome": round(float(yte.mean()), 3),
           "auc": round(float(roc_auc_score(yte, p)), 3), "auc_simple_rule": round(float(roc_auc_score(yte, rule)), 3),
           "share_of_bad_outcomes_in_top_20pct": round(float(yte[top].sum() / max(yte.sum(), 1)), 3),
           "features": FEATS, "train_seconds": round(time.time() - t0)}
    print(json.dumps(res, indent=2))
    save({"model": model, "features": FEATS, "kind": kind}, "risk.pkl")
    json.dump(res, open(os.path.join(MODELS, "risk_metrics.json"), "w"), indent=2)
    print("saved models/risk.pkl")
