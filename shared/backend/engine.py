"""
engine.py - the live matching engine behind the web app.

Holds all reports and found people, the score matrix (every report vs every found person), the decisions
authorities have made, and saves new records to a small JSON file so a restart loses nothing.
"""
import json
import os
import re
import threading
import time

import joblib
import numpy as np
import pandas as pd

import features as FT
from extract import Extractor
from scorer import Scorer, device_mode
from store import read_json, state_key as _state_key, write_json

MISSING_COLS = ["id", "age_min", "age_max", "gender", "height_cm", "hair", "clothing", "marks",
                "last_seen_place", "last_seen_time", "description", "contact", "auto_filled"]
FOUND_COLS = ["id", "age_min", "age_max", "gender", "height_cm", "hair", "clothing", "marks",
              "found_place", "found_time", "current_location", "description",
              "source", "reporter_name", "reporter_phone",      # source: "authority" or "public"
              "auto_filled"]                                   # boxes read from the description, e.g. "hair,marks"
STATUS_TEXT = {
    "searching": "We are searching. We will contact you if there is news.",
    "possible_match": "A possible match is being reviewed by an authority. This is not a confirmation.",
    "reunited": "An authority has confirmed a match and will contact you.",
}


def _clean_text(v, n=500):
    if v is None:
        return ""
    return re.sub(r"[\x00-\x1f\x7f]", " ", str(v)).strip()[:n]


def _py(v):
    """numpy / pandas value -> plain JSON-safe python value"""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return None if np.isnan(v) else float(v)
    return v


def _rec(row, cols):
    return {c: _py(row[c]) for c in cols}


class Engine:
    def __init__(self, data_dir, model_dir, state_path, backend="auto", log=print, preload=None):
        self.log = log
        # PRELOAD=full (default): the CSV reports and found people are loaded at start-up.
        # PRELOAD=none: start completely empty (for a live demo); only what is filed afterwards exists.
        self.preload = (preload or os.environ.get("PRELOAD", "full")).strip().lower()
        if self.preload not in ("full", "none"):
            raise ValueError('PRELOAD must be "full" or "none".')
        self.lock = threading.RLock()
        self.model_dir, self.state_path = model_dir, state_path
        self.key = _state_key()                                 # None = plain JSON state file
        self.meta = json.load(open(os.path.join(model_dir, "meta.json")))
        self.threshold = float(self.meta["review_threshold"])
        self.art = joblib.load(os.path.join(model_dir, "artifacts.joblib"))
        self.scorer = Scorer(os.path.join(model_dir, "scorer.npz"), backend=backend, log=log)
        self.extractor = Extractor(log=log)                      # fills empty hair / clothing / marks from the description

        rd = lambda n: pd.read_csv(os.path.join(data_dir, n))
        missing, found = rd("missing.csv"), rd("found.csv")
        found["source"], found["reporter_name"], found["reporter_phone"] = "authority", None, None
        missing["auto_filled"], found["auto_filled"] = "", ""
        self.places = rd("places.csv")
        self.demo_cases = json.load(open(os.path.join(model_dir, "demo_cases.json")))
        hold_m = {c["missing_id"] for c in self.demo_cases}
        hold_f = {c["found_id"] for c in self.demo_cases}      # kept out so they can be submitted live in the demo
        self.preloaded_m = set(missing["id"]) - hold_m
        self.preloaded_f = set(found["id"]) - hold_f
        self.mdf = missing[~missing["id"].isin(hold_m)][MISSING_COLS].reset_index(drop=True)
        self.fdf = found[~found["id"].isin(hold_f)][FOUND_COLS].reset_index(drop=True)
        self.next_m = int(missing["id"].str[1:].astype(int).max()) + 1
        self.next_f = int(found["id"].str[1:].astype(int).max()) + 1
        if self.preload == "none":
            self.preloaded_m, self.preloaded_f = set(), set()
            self.mdf, self.fdf = self.mdf.iloc[0:0].copy(), self.fdf.iloc[0:0].copy()
            self.next_m = self.next_f = 1
            log("[engine] PRELOAD=none: starting with no reports and no found people")
        self.decisions = {}                                    # missing_id -> {"confirmed": fid|None, "rejected": [fid]}
        self.last_rescan = {}
        self._load_state()
        self.rescan()

    # ------------------------------------------------------------------ persistence
    def _load_state(self):
        if not os.path.exists(self.state_path):
            return
        st = read_json(self.state_path, self.key)
        if st["missing"]:
            m = pd.DataFrame(st["missing"]).reindex(columns=MISSING_COLS)
            m["auto_filled"] = m["auto_filled"].fillna("")
            self.mdf = pd.concat([self.mdf, m], ignore_index=True)
        if st["found"]:
            f = pd.DataFrame(st["found"]).reindex(columns=FOUND_COLS)       # older state files have no source column
            f["source"] = f["source"].fillna("authority")
            f["auto_filled"] = f["auto_filled"].fillna("")
            self.fdf = pd.concat([self.fdf, f], ignore_index=True)
        self.decisions = st.get("decisions", {})
        self.next_m, self.next_f = max(self.next_m, st["next_m"]), max(self.next_f, st["next_f"])
        self.log(f"[engine] restored {len(st['missing'])} new reports, {len(st['found'])} new found people, "
                 f"{len(self.decisions)} decisions from {self.state_path}")

    def _save_state(self):
        m = self.mdf[~self.mdf["id"].isin(self.preloaded_m)]
        f = self.fdf[~self.fdf["id"].isin(self.preloaded_f)]
        st = {"missing": [_rec(r, MISSING_COLS) for _, r in m.iterrows()],
              "found": [_rec(r, FOUND_COLS) for _, r in f.iterrows()],
              "decisions": self.decisions, "next_m": self.next_m, "next_f": self.next_f}
        write_json(self.state_path, st, self.key)

    # ------------------------------------------------------------------ validation
    def _clean(self, body, kind):
        if not isinstance(body, dict):
            raise ValueError("Send a JSON object.")
        try:
            a, b = int(float(body.get("age_min"))), int(float(body.get("age_max")))
        except (TypeError, ValueError):
            raise ValueError("age_min and age_max are required numbers.")
        if not (0 <= a <= 120 and 0 <= b <= 120):
            raise ValueError("Ages must be between 0 and 120.")
        a, b = min(a, b), max(a, b)
        g = _clean_text(body.get("gender"), 20).lower()
        rec = {"age_min": a, "age_max": b, "gender": g if g in FT.GENDER_CODE else "unknown"}
        try:
            h = body.get("height_cm")
            h = float(h) if h not in (None, "") else None
            rec["height_cm"] = h if h is not None and 30 <= h <= 250 else None
        except (TypeError, ValueError):
            rec["height_cm"] = None
        for k in ("hair", "clothing", "marks", "description"):
            rec[k] = _clean_text(body.get(k))
        pk, tk = ("last_seen_place", "last_seen_time") if kind == "missing" else ("found_place", "found_time")
        rec[pk] = _clean_text(body.get(pk), 120)
        if not rec[pk]:
            raise ValueError(f"{pk} is required.")
        try:
            t = pd.Timestamp(_clean_text(body.get(tk), 40))
            if pd.isna(t):
                raise ValueError
            rec[tk] = t.tz_localize(None).strftime("%Y-%m-%dT%H:%M") if t.tzinfo is None else t.tz_convert(None).strftime("%Y-%m-%dT%H:%M")
        except (ValueError, TypeError):
            raise ValueError(f"{tk} is required, as a date and time like 2026-10-16T18:00.")
        if kind == "missing":
            rec["contact"] = _clean_text(body.get("contact"), 100)
        else:
            rec["current_location"] = _clean_text(body.get("current_location"), 120)
        rec["place_recognised"] = self.art.place_index(rec[pk]) >= 0
        rec["auto_filled"] = ",".join(self.extractor.fill(rec))      # boxes left empty are read from the description
        return rec

    # ------------------------------------------------------------------ scoring
    def _score_block(self, mdf, fdf):
        if len(mdf) == 0 or len(fdf) == 0:                       # nothing to compare yet
            return np.zeros((len(mdf), len(fdf)), np.float32), 0.0, 0.0
        t0 = time.time()
        X = FT.pair_tensor(FT.build_side(mdf, "missing", self.art), FT.build_side(fdf, "found", self.art))
        t1 = time.time()
        S = self.scorer.predict(X.reshape(-1, X.shape[-1])).reshape(len(mdf), len(fdf))
        return S, t1 - t0, time.time() - t1

    def rescan(self):
        """Re-score every report against every found person (the big batch job)."""
        with self.lock:
            self.S, t_feat, t_score = self._score_block(self.mdf, self.fdf)
            pairs = int(self.S.size)
            self.last_rescan = {"reports": len(self.mdf), "found_people": len(self.fdf), "pairs": pairs,
                                "feature_seconds": round(t_feat, 3), "scoring_seconds": round(t_score, 3),
                                "scoring_pairs_per_sec": int(pairs / max(t_score, 1e-9)),
                                "scoring_mode": self.scorer.last.get("mode"), "at": time.strftime("%H:%M:%S")}
            self.log(f"[engine] rescan {pairs} pairs: features {t_feat:.2f}s, scoring {t_score:.3f}s ({self.last_rescan['scoring_mode']})")
            return dict(self.last_rescan)

    # ------------------------------------------------------------------ adding records
    def add_missing(self, body):
        with self.lock:
            rec = self._clean(body, "missing")
            place_ok = rec.pop("place_recognised")
            rec["id"] = f"M{self.next_m}"; self.next_m += 1
            self.mdf = pd.concat([self.mdf, pd.DataFrame([rec])[MISSING_COLS]], ignore_index=True)
            row, _, _ = self._score_block(self.mdf.tail(1), self.fdf)
            self.S = np.vstack([self.S, row])
            self._save_state()
            return {"id": rec["id"], "status": self.status(rec["id"]), "place_recognised": place_ok}

    def add_found(self, body, source="authority"):
        with self.lock:
            rec = self._clean(body, "found")
            place_ok = rec.pop("place_recognised")
            rec["source"] = source
            if source == "public":                              # kept for the authority only, never shown to families
                rec["reporter_name"] = _clean_text(body.get("reporter_name"), 100) or None
                rec["reporter_phone"] = _clean_text(body.get("reporter_phone"), 50) or None
            else:
                rec["reporter_name"] = rec["reporter_phone"] = None
            rec["id"] = f"F{self.next_f}"; self.next_f += 1
            self.fdf = pd.concat([self.fdf, pd.DataFrame([rec])[FOUND_COLS]], ignore_index=True)
            col, _, _ = self._score_block(self.mdf, self.fdf.tail(1))
            self.S = np.hstack([self.S, col])
            self._save_state()
            return {"id": rec["id"], "place_recognised": place_ok, "flagged_reports": int((col[:, 0] >= self.threshold).sum())}

    # ------------------------------------------------------------------ queries
    @staticmethod
    def _top(row):
        return float(row.max()) if len(row) else 0.0

    def _index(self, mid):
        hit = np.flatnonzero(self.mdf["id"].to_numpy() == mid)
        return int(hit[0]) if len(hit) else None

    def _claimed(self):
        return {d["confirmed"]: m for m, d in self.decisions.items() if d.get("confirmed")}

    def _masked_row(self, i, claimed):
        row = self.S[i].copy()
        mid = self.mdf["id"].iat[i]
        own = self.decisions.get(mid, {})
        fids = self.fdf["id"].to_numpy()
        for fid, owner in claimed.items():
            if owner != mid:
                row[fids == fid] = -1
        for fid in own.get("rejected", []):
            row[fids == fid] = -1
        return row

    def status(self, mid):
        i = self._index(mid)
        if i is None:
            return None
        if self.decisions.get(mid, {}).get("confirmed"):
            return "reunited"
        return "possible_match" if self._top(self._masked_row(i, self._claimed())) >= self.threshold else "searching"

    def public_status(self, mid):
        s = self.status(mid)
        return None if s is None else {"id": mid, "status": s, "message": STATUS_TEXT[s]}

    def list_missing(self):
        with self.lock:
            claimed = self._claimed()
            out = []
            for i, r in self.mdf.iterrows():
                row = self._masked_row(i, claimed)
                mid = r["id"]
                s = "reunited" if self.decisions.get(mid, {}).get("confirmed") else ("possible_match" if self._top(row) >= self.threshold else "searching")
                age = f"{r['age_min']}" if r["age_min"] == r["age_max"] else f"{r['age_min']}-{r['age_max']}"
                rec = _rec(r, MISSING_COLS)
                rec.update({"status": s, "flagged": s == "possible_match", "top_score": min(99, int(round(100 * self._top(row)))),
                            "summary": f"{r['gender']}, {age} yrs, {_clean_text(r['clothing'], 50) or 'clothing not given'}, last seen {r['last_seen_place']}"})
                out.append(rec)
            order = {"possible_match": 0, "searching": 1, "reunited": 2}
            out.sort(key=lambda d: (order[d["status"]], -d["top_score"]))
            return out

    def matches(self, mid, k=10):
        """Top candidates by raw score. Rejected and claimed people stay in the list (marked) so a reviewer can undo."""
        with self.lock:
            i = self._index(mid)
            if i is None:
                return None
            claimed = self._claimed()
            own = self.decisions.get(mid, {})
            rejected, conf = set(own.get("rejected", [])), own.get("confirmed")
            order = list(np.argsort(-self.S[i])[:k])
            if conf:                                           # a confirmed match always comes first
                j = int(np.flatnonzero(self.fdf["id"].to_numpy() == conf)[0])
                order = [j] + [x for x in order if x != j][:k - 1]
            mrec = self.mdf.iloc[i]
            X = (FT.pair_tensor(FT.build_side(self.mdf.iloc[[i]], "missing", self.art),
                                FT.build_side(self.fdf.iloc[order], "found", self.art))[0] if order else [])
            cands = []
            for n, j in enumerate(order):
                frec = self.fdf.iloc[j]
                fid = frec["id"]
                owner = claimed.get(fid)
                cands.append({"found_id": fid, "score": min(99, int(round(100 * float(self.S[i, j])))),
                              "flagged": bool(self.S[i, j] >= self.threshold),
                              "decision": "confirmed" if fid == conf else ("rejected" if fid in rejected else None),
                              "claimed_by": owner if owner and owner != mid else None,
                              "reasons": FT.reasons(mrec.to_dict(), frec.to_dict(), X[n]),
                              "found": _rec(frec, FOUND_COLS)})
            return {"missing_id": mid, "status": self.status(mid), "missing": _rec(mrec, MISSING_COLS),
                    "review_threshold": int(round(100 * self.threshold)), "candidates": cands,
                    "rejected": sorted(rejected)}

    def decide(self, mid, fid, decision):
        with self.lock:
            if self._index(mid) is None:
                raise KeyError("Unknown report.")
            if fid not in set(self.fdf["id"]):
                raise KeyError("Unknown found person.")
            if decision not in ("confirm", "reject", "undo"):
                raise ValueError('decision must be "confirm", "reject" or "undo".')
            d = self.decisions.setdefault(mid, {"confirmed": None, "rejected": []})
            if decision == "confirm":
                owner = self._claimed().get(fid)
                if owner and owner != mid:
                    raise PermissionError(f"That person is already confirmed as the match for report {owner}.")
                if d.get("confirmed") and d["confirmed"] != fid:
                    raise PermissionError(f"This report already has a confirmed match ({d['confirmed']}). Undo it first.")
                d["confirmed"] = fid
                d["rejected"] = [x for x in d["rejected"] if x != fid]
            elif decision == "reject":
                if d.get("confirmed") == fid:
                    d["confirmed"] = None
                if fid not in d["rejected"]:
                    d["rejected"].append(fid)
            else:
                if d.get("confirmed") == fid:
                    d["confirmed"] = None
                d["rejected"] = [x for x in d["rejected"] if x != fid]
            self._save_state()
            return {"missing_id": mid, "found_id": fid, "decision": decision, "status": self.status(mid)}

    # ------------------------------------------------------------------ info for the platform page
    def benchmark(self, bench_path):
        out = {}
        if os.path.exists(bench_path):
            out = json.load(open(bench_path))
        tr = self.meta["test_results"]
        out["live_rescan"] = self.last_rescan
        out["scorer"] = {**self.scorer.info(), "mode_now": device_mode(self.scorer.tf is not None),
                         "model": self.meta["model"], "n_features": self.meta["n_features"]}
        out["quality"] = {"note": "Held-out synthetic reports the model never trained on.",
                          "reports_evaluated": self.meta["test_results"][next(iter(tr))]["queries"],
                          "found_pool": self.meta["found_pool"],
                          "results": {k: {m: round(v[m], 3) for m in ("top1", "top5", "top10", "mrr")} for k, v in tr.items()},
                          "ablation": {k: {m: round(v[m], 3) for m in ("top1", "top5")} for k, v in self.meta["ablation_test"].items()},
                          "review_policy": self.meta["review_policy_test"]}
        pick = lambda word: next((v for k, v in tr.items() if k.startswith(word) or word in k), None)
        eng_r, kw_r = pick("DEPLOYED"), pick("keyword")
        if eng_r and kw_r:                                      # the shape the front end's platform page reads
            out["accuracy"] = {"cases": eng_r["queries"], "engine": {"top1": round(eng_r["top1"], 3), "top5": round(eng_r["top5"], 3)},
                               "keyword": {"top1": round(kw_r["top1"], 3), "top5": round(kw_r["top5"], 3)}}
        lr = self.last_rescan
        if lr:
            out["speed"] = {"pairs": lr["pairs"], "full_rescan_seconds": round(lr["feature_seconds"] + lr["scoring_seconds"], 3),
                            "scoring_seconds": lr["scoring_seconds"]}
        out["note"] = ("Accuracy: held-out synthetic reports the scorer never trained on. Speed: measured live on this server. "
                       "Chip: only shown when bench_scorer.py has been run on this server. All data is synthetic.")
        return out

    def get_demo_cases(self):
        """Held-out synthetic pairs for a live demo, plus what would happen if they were submitted now."""
        def body(d):
            return {k: v for k, v in d.items() if v is not None}
        out = []
        with self.lock:
            for c in self.demo_cases:
                m = self._clean(c["missing"], "missing"); m.pop("place_recognised"); m["id"] = "demo"
                f = self._clean(c["found"], "found"); f.pop("place_recognised"); f["id"] = "demo"
                mdf = pd.DataFrame([m])[MISSING_COLS]
                before, _, _ = self._score_block(mdf, self.fdf)                       # report vs people already in the system
                own, _, _ = self._score_block(mdf, pd.DataFrame([f]).reindex(columns=FOUND_COLS))     # report vs its true match
                rank = 1 + int((before[0] > own[0, 0]).sum())
                n = len(out) + 1
                mm = c["missing"]
                out.append({"id": f"D{n}", "title": f"Demo case {n}: {mm['gender']}, {mm['age_min']}-{mm['age_max']}, last seen {mm['last_seen_place']}",
                            "missing": body(c["missing"]), "found": body(c["found"]),
                            "status_when_submitted": "possible_match" if self._top(before[0]) >= self.threshold else "searching",
                            "true_match_score": min(99, int(round(100 * float(own[0, 0])))),
                            "true_match_rank_after_found_is_added": rank,
                            "good_for_live_demo": bool(self._top(before[0]) < self.threshold and rank == 1 and own[0, 0] >= self.threshold)})
        return out
