"""Shared helpers for the Reunite models: loading data, name normalisation, pair features, model choice."""
import csv, json, math, os, re, unicodedata, pickle
from datetime import datetime
from difflib import SequenceMatcher

DATA = os.environ.get("REUNITE_DATA", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reunite_universal"))
MODELS = os.environ.get("REUNITE_MODELS", os.path.join(os.path.dirname(os.path.abspath(__file__)), "models"))
os.makedirs(MODELS, exist_ok=True)


# ---------------------------------------------------------------- loading
def load_csv(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return list(csv.DictReader(f))

def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f]

def load_extractions():
    """record id -> extracted JSON.
    Uses the LLM's own predictions (models/extracted.jsonl, written by eval_extraction.py) where they exist,
    otherwise the gold labels, so the matcher can be built before the LLM is fine-tuned."""
    ex, src = {}, {}
    for s in ("train", "val", "test"):
        p = os.path.join(DATA, f"llm_{s}.jsonl")
        if os.path.exists(p):
            for r in load_jsonl(p):
                ex[r["id"]] = r["output"]; src[r["id"]] = "gold"
    pred = os.path.join(MODELS, "extracted.jsonl")
    if os.path.exists(pred):
        for r in load_jsonl(pred):
            if r.get("output"):
                ex[r["id"]] = r["output"]; src[r["id"]] = "llm"
    return ex, src

def meta():
    with open(os.path.join(DATA, "meta.json"), encoding="utf-8") as f:
        return json.load(f)

def ts(s):
    return datetime.fromisoformat(s).timestamp() / 3600.0  # hours

def km(a, b, c, d):
    r = math.radians
    h = math.sin(r(c - a) / 2) ** 2 + math.cos(r(a)) * math.cos(r(c)) * math.sin(r(d - b) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(min(1, h)))


# ---------------------------------------------------------------- names
ABBREV = {"ma": "maria", "mohd": "muhammad", "md": "muhammad", "bdr": "bahadur", "st": "saint"}
PARTICLES = {"da", "dos", "de", "la", "del", "di", "el", "al", "ben", "ait", "van", "von"}

def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))

def norm_token(t):
    t = strip_accents(t.lower())
    t = re.sub(r"[^a-z]", "", t)
    t = ABBREV.get(t, t)
    for a, b in (("ph", "f"), ("kh", "k"), ("gh", "g"), ("sh", "s"), ("ou", "u"), ("ee", "i"), ("oo", "u"), ("y", "i"), ("w", "v"), ("q", "k"), ("z", "s")):
        t = t.replace(a, b)
    t = re.sub(r"(.)\1+", r"\1", t)          # collapse doubled letters
    if len(t) > 3 and t.endswith("h"):
        t = t[:-1]
    return t

def name_tokens(s):
    if not s:
        return []
    toks = [norm_token(x) for x in re.split(r"[\s\-.]+", s)]
    return [t for t in toks if t and t not in PARTICLES]

def name_sim(a, b):
    """Average best fuzzy match of the shorter name's tokens against the longer one (0..1)."""
    if not a or not b:
        return None
    s, l = (a, b) if len(a) <= len(b) else (b, a)
    return sum(max(SequenceMatcher(None, x, y).ratio() for y in l) for x in s) / len(s)


# ---------------------------------------------------------------- records
def missing_records():
    ex, src = load_extractions()
    out = []
    for r in load_csv("missing_reports.csv"):
        x = ex.get(r["report_id"])
        if not x:
            continue
        out.append({"id": r["report_id"], "country": r["country"], "x": x, "lat": float(r["last_seen_lat"]), "lon": float(r["last_seen_lon"]),
                    "t": ts(r["last_seen_time"]), "family_id": r["family_id"] if r["via_family_registration"] == "True" else "",
                    "name_t": name_tokens(x.get("name_latin")), "raw_t": set(re.findall(r"\w+", (x.get("name") or "").lower()))})
    return out

def found_records():
    ex, src = load_extractions()
    out = []
    for r in load_csv("found_reports.csv"):
        x = ex.get(r["found_id"])
        if not x:
            continue
        out.append({"id": r["found_id"], "country": r["country"], "x": x, "lat": float(r["found_lat"]), "lon": float(r["found_lon"]),
                    "t": ts(r["found_at"]), "site": r["site"], "condition": r["condition"], "consent": r["consent"],
                    "name_t": name_tokens(x.get("name_latin")), "raw_t": set(re.findall(r"\w+", (x.get("name") or "").lower()))})
    return out

def truth():
    return {r["record_id"]: r["person_id"] for r in load_csv("ground_truth.csv")}


# ---------------------------------------------------------------- pair features (missing report vs found report)
FEATURES = ["name_sim", "name_exact_overlap", "first_sim", "last_sim", "name_missing", "age_gap", "age_mid_diff", "age_missing",
            "gender_match", "cloth_jacc", "cloth_item_jacc", "cloth_missing", "marks_jacc", "marks_extra", "marks_missing",
            "med_jacc", "lang_jacc", "place_same", "dist_km", "hours_gap"]

def jacc(a, b):
    a, b = set(a), set(b)
    if not a or not b:
        return -1.0
    return len(a & b) / len(a | b)

def pair_features(m, f):
    mx, fx = m["x"], f["x"]
    ns = name_sim(m["name_t"], f["name_t"])
    ov = len(set(m["name_t"]) & set(f["name_t"]))
    first = SequenceMatcher(None, m["name_t"][0], f["name_t"][0]).ratio() if m["name_t"] and f["name_t"] else -1
    last = SequenceMatcher(None, m["name_t"][-1], f["name_t"][-1]).ratio() if len(m["name_t"]) > 1 and len(f["name_t"]) > 1 else -1
    if mx.get("age_min") is not None and fx.get("age_min") is not None:
        gap = max(0, max(mx["age_min"], fx["age_min"]) - min(mx["age_max"], fx["age_max"]))
        mid = abs((mx["age_min"] + mx["age_max"]) / 2 - (fx["age_min"] + fx["age_max"]) / 2)
        am = 0
    else:
        gap, mid, am = -1, -1, 1
    g = 0 if not mx.get("gender") or not fx.get("gender") else (1 if mx["gender"] == fx["gender"] else -1)
    mc, fc = mx.get("clothing") or [], fx.get("clothing") or []
    items = lambda L: [c.split(" ", 1)[-1] for c in L]
    mm, fm = mx.get("marks") or [], fx.get("marks") or []
    extra = len(set(fm) - set(mm)) if mm and fm else -1
    return [ns if ns is not None else -1, ov, first, last, int(ns is None), gap, mid, am,
            g, jacc(mc, fc), jacc(items(mc), items(fc)), int(not mc or not fc), jacc(mm, fm), extra, int(not mm or not fm),
            jacc(mx.get("medical") or [], fx.get("medical") or []), jacc(mx.get("languages") or [], fx.get("languages") or []),
            -1 if not mx.get("place") or not fx.get("place") else int(mx["place"] == fx["place"]),
            km(m["lat"], m["lon"], f["lat"], f["lon"]), f["t"] - m["t"]]

def quick_score(m, f):
    """Cheap filter used to pick ~40 candidates per missing report before the full model scores them."""
    mx, fx = m["x"], f["x"]
    if f["t"] < m["t"] - 1:
        return None
    if mx.get("gender") and fx.get("gender") and mx["gender"] != fx["gender"]:
        return None
    if mx.get("age_min") is not None and fx.get("age_min") is not None:
        if max(mx["age_min"], fx["age_min"]) - min(mx["age_max"], fx["age_max"]) > 15:
            return None
    s = 3 * len(set(m["name_t"]) & set(f["name_t"]))
    if m["name_t"] and f["name_t"] and m["name_t"][0][:3] == f["name_t"][0][:3]:
        s += 1.5
    s += len(set(mx.get("clothing") or []) & set(fx.get("clothing") or []))
    s += 2 * len(set(mx.get("marks") or []) & set(fx.get("marks") or []))
    s -= km(m["lat"], m["lon"], f["lat"], f["lon"]) / 200
    return s

def candidates(m, pool, k=40):
    scored = [(q, f) for f in pool if (q := quick_score(m, f)) is not None]
    scored.sort(key=lambda z: -z[0])
    return [f for _, f in scored[:k]]


# ---------------------------------------------------------------- model choice
def make_classifier(small=False):
    """IBM Snap ML if installed (runs on IBM Z / LinuxONE), else scikit-learn.
    small=True: a simpler, more regularised model for small datasets (risk, location)."""
    rounds, depth, lr = (120, 3, 0.05) if small else (300, 6, 0.1)
    try:
        from snapml import BoostingMachineClassifier
        return BoostingMachineClassifier(num_round=rounds, max_depth=depth, learning_rate=lr, n_jobs=os.cpu_count() or 1), "snapml.BoostingMachineClassifier"
    except Exception:
        from sklearn.ensemble import HistGradientBoostingClassifier
        return HistGradientBoostingClassifier(max_iter=rounds, learning_rate=lr, max_depth=depth, min_samples_leaf=40 if small else 20,
                                              random_state=0), "sklearn.HistGradientBoostingClassifier"

def proba(model, X):
    import numpy as np
    p = model.predict_proba(np.asarray(X, dtype="float32"))
    return p[:, 1] if p.ndim == 2 else p

def save(obj, name):
    with open(os.path.join(MODELS, name), "wb") as f:
        pickle.dump(obj, f)

def load(name):
    with open(os.path.join(MODELS, name), "rb") as f:
        return pickle.load(f)

def split_of(country):
    return meta()["scenarios"][country]["split"]
