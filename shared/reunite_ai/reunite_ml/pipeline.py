"""The full Reunite pipeline on new reports, with timings.
  python pipeline.py              # matcher + location + risk on 200 unseen-country reports (fast)
  python pipeline.py --llm        # also runs Granite on the report text (slower, uses the fine-tuned adapter)
"""
import argparse, json, time, statistics
import numpy as np
from common import missing_records, found_records, candidates, pair_features, proba, load, split_of, meta, km

ap = argparse.ArgumentParser()
ap.add_argument("--n", type=int, default=200)
ap.add_argument("--llm", action="store_true")
a = ap.parse_args()

matcher, location, risk = load("matcher.pkl"), load("location.pkl"), load("risk.pkl")
from train_location import features as loc_features
from train_risk import features as risk_features
META = meta()
F = found_records()
pool = {}
for f in F:
    pool.setdefault(f["country"], []).append(f)
reports = [m for m in missing_records() if split_of(m["country"]) == "test"][:a.n]

llm = None
if a.llm:
    from llm_common import load_model, extract, ADAPTER_DIR
    from common import load_csv, name_tokens
    tok, model = load_model(adapter=ADAPTER_DIR)
    texts = {r["report_id"]: r["text"] for r in load_csv("missing_reports.csv")}

times = {"llm": [], "match": [], "location": [], "risk": []}
example = None
for m in reports:
    if a.llm:
        t = time.perf_counter(); x, _ = extract(tok, model, texts[m["id"]]); times["llm"].append(time.perf_counter() - t)
        if x:
            m = {**m, "x": x, "name_t": name_tokens(x.get("name_latin"))}
    t = time.perf_counter()
    cands = candidates(m, pool[m["country"]])
    scores = proba(matcher["model"], [pair_features(m, f) for f in cands]) if cands else []
    top = sorted(zip(scores, cands), key=lambda z: -z[0])[:3]
    times["match"].append(time.perf_counter() - t)
    t = time.perf_counter()
    names, X, _ = loc_features(m)
    lp = proba(location["model"], X); where = [names[i] for i in np.argsort(-lp)[:3]]
    times["location"].append(time.perf_counter() - t)
    t = time.perf_counter()
    hours = 24.0
    rp = float(proba(risk["model"], [risk_features(m, hours)])[0])
    times["risk"].append(time.perf_counter() - t)
    if example is None and top:
        example = {"report": m["id"], "extracted": m["x"], "top_matches": [{"found_id": f["id"], "score": round(float(s), 3)} for s, f in top],
                   "call_these_sites_first": where, "risk_if_missing_24h": round(rp, 3)}

ms = lambda L: round(1000 * statistics.mean(L), 1) if L else None
res = {"reports": len(reports), "avg_ms": {k: ms(v) for k, v in times.items()},
       "avg_ms_without_llm": round(ms(times["match"]) + ms(times["location"]) + ms(times["risk"]), 1),
       "matcher_model": matcher["kind"], "example": example}
print(json.dumps(res, indent=2, ensure_ascii=False))
