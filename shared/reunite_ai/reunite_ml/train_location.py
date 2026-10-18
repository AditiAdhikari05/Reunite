"""Model 3: where is this person most likely to be?
For a missing report, ranks every shelter and hospital in the area. Responders call the top 3 first.
Learns from where found people actually ended up. Tests on unseen countries.
Run:  python train_location.py
"""
import json, os, time
import numpy as np
from common import missing_records, load_csv, truth, meta, km, make_classifier, proba, save, split_of, MODELS

t0 = time.time()
T, META = truth(), meta()
HAZ = ["flood", "flash flood", "hurricane", "earthquake", "typhoon"]
FEATS = ["dist_km", "dist_rank", "dist_minus_nearest", "log_dist", "nearest_hospital", "nearest_shelter", "is_hospital", "medical_flag", "medical_x_hospital", "slow_mobility", "slow_x_dist",
         "downstream", "near_home", "home_known", "age"] + [f"hazard_{h}" for h in HAZ]

homes = {r["family_id"]: r["home_place"] for r in load_csv("families.csv")}
site_of = {}  # person -> first site they were found at
for r in sorted(load_csv("found_reports.csv"), key=lambda r: r["found_at"]):
    if r["site"] and T[r["found_id"]] not in site_of:
        site_of[T[r["found_id"]]] = r["site"]

def features(m):
    sc = META["scenarios"][m["country"]]
    sites, hz = sc["sites"], sc["hazard"]
    x = m["x"]
    age = ((x["age_min"] + x["age_max"]) / 2) if x.get("age_min") is not None else -1
    med = int(bool(set(x.get("medical") or []) & {"diabetes", "heart condition", "pregnant", "epilepsy"}))
    slow = int((0 <= age < 12) or age >= 70 or bool(set(x.get("marks") or []) & {"walks with a limp", "uses a walking stick"}))
    home = homes.get(m["family_id"]) if m["family_id"] else None
    hll = sc["places"].get(home) if home else None
    d = [km(m["lat"], m["lon"], s["lat"], s["lon"]) for s in sites]
    rank = np.argsort(np.argsort(d)) + 1
    dmin = min(d)
    near_h = min((x for x, s in zip(d, sites) if s["kind"] == "hospital"), default=1e9)
    near_s = min((x for x, s in zip(d, sites) if s["kind"] != "hospital"), default=1e9)
    rows = []
    for s, dist, rk in zip(sites, d, rank):
        hosp = int(s["kind"] == "hospital")
        rows.append([dist, rk, dist - dmin, float(np.log1p(dist)), int(hosp and dist == near_h), int(not hosp and dist == near_s), hosp, med, med * hosp, slow, slow * dist, int(hz == "flash flood" and s["lat"] < m["lat"] - .02),
                     int(km(hll[0], hll[1], s["lat"], s["lon"]) < 12) if hll else -1, int(hll is not None), age] + [int(hz == h) for h in HAZ])
    return [s["name"] for s in sites], rows, d

if __name__ == "__main__":
    data = {"train": [], "test": []}
    for m in missing_records():
        target = site_of.get(T[m["id"]])
        if not target:
            continue
        names, X, d = features(m)
        data["test" if split_of(m["country"]) == "test" else "train"].append((names, X, [int(n == target) for n in names], d))

    Xtr = np.array([x for _, X, _, _ in data["train"] for x in X], dtype="float32")
    ytr = np.array([y for _, _, Y, _ in data["train"] for y in Y])
    model, kind = make_classifier(small=True)
    model.fit(Xtr, ytr)

    def evaluate(rows):
        top1 = top3 = near1 = near3 = 0
        rand3 = 0.0
        for names, X, Y, d in rows:
            p = proba(model, X); order = np.argsort(-p); near = np.argsort(d)
            truth_i = Y.index(1)
            top1 += order[0] == truth_i; top3 += truth_i in order[:3]
            near1 += near[0] == truth_i; near3 += truth_i in near[:3]
            rand3 += min(3, len(names)) / len(names)
        n = len(rows)
        return {"cases": n, "model_top1": round(top1 / n, 3), "model_top3": round(top3 / n, 3),
                "nearest_site_top1": round(near1 / n, 3), "nearest_site_top3": round(near3 / n, 3), "random_top3": round(rand3 / n, 3)}

    res = {"model": kind, "test_countries": ["MA", "PH"], **evaluate(data["test"]), "features": FEATS, "train_seconds": round(time.time() - t0)}
    print(json.dumps(res, indent=2))
    save({"model": model, "features": FEATS, "kind": kind}, "location.pkl")
    json.dump(res, open(os.path.join(MODELS, "location_metrics.json"), "w"), indent=2)
    print("saved models/location.pkl")
