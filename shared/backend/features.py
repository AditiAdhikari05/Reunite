"""
features.py - turns a missing-person report and a found-person record into numbers a model can compare.

Everything here is plain numpy/scipy/scikit-learn (all preinstalled in the LinuxONE Jupyter image).
The key function is pair_tensor(M, F): for every (missing, found) combination it returns a vector of
FEATURES numbers, computed with matrix maths so all 400 x 600 = 240,000 pairs take about a second.

The word lists below (colour families, garment families, mark types) are hand-written from general
knowledge. They are NOT learned from the truth labels.
"""
import difflib
import re

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

FEATURES = [
    # who: gender, age, height
    "g_same", "g_conflict", "g_unk",
    "age_overlap", "age_gap_norm", "age_mid_diff_norm", "age_child_adult_conflict",
    "h_known", "h_diff_norm",
    # hair
    "hair_color_known", "hair_color_sim", "hair_len_known", "hair_len_sim", "hair_char_sim",
    # clothing
    "cloth_known", "cloth_family", "cloth_sub", "cloth_color", "cloth_item", "cloth_char_sim",
    # distinguishing marks
    "marks_known", "marks_one_blank", "marks_type", "marks_typeloc", "marks_side_match",
    "marks_side_conflict", "marks_char_sim",
    # free-text description
    "desc_word_sim", "desc_char_sim",
    # where and when
    "place_known", "km_norm", "gap_negative", "speed_norm",
]
FEATURE_GROUPS = {
    "demographics (gender, age, height)": FEATURES[0:9],
    "appearance text (hair, clothing, marks)": FEATURES[9:27],
    "free-text description": FEATURES[27:29],
    "place and time": FEATURES[29:33],
}
COL = {n: i for i, n in enumerate(FEATURES)}

# ----------------------------------------------------------------------------- vocabulary
GENDER_CODE = {"unknown": 0, "female": 1, "male": 2, "other": 3}

# hair colour on a 0 (black) .. 7 (white) darkness scale; first matching pattern wins
HAIR_COLOR = [
    (r"salt[- ]and[- ]pepper", 6.0), (r"grey[- ]white|gray[- ]white|silver[- ]white", 6.5), (r"snow", 7.0),
    (r"jet[- ]?black|\bjet\b|raven|ebony|very dark", 0.0), (r"near[- ]black", 0.5),
    (r"dark brown|deep brown|espresso", 1.0), (r"light brown|light chestnut", 3.5), (r"dark blond|dirty blond|honey", 4.0),
    (r"platinum", 6.5), (r"black", 0.0), (r"chestnut", 2.0), (r"brunette|brown", 2.0), (r"auburn", 3.0),
    (r"ginger|\bred\b|reddish|copper|titian", 3.0),
    (r"sandy", 4.5), (r"blond|flaxen|golden|\bfair\b", 5.0), (r"silver", 6.0), (r"grey|gray|greying|graying", 6.0), (r"white", 7.0),
    (r"\bdark\b", 1.0), (r"\blight\b", 4.0),
]
# hair length on a 0 (bald) .. 7 (waist length) scale
HAIR_LEN = [
    (r"bald", 0.0), (r"cropped short|above the ears|pixie", 2.0),
    (r"very short|buzz|close[- ]cut|cropped|shaved|crew[- ]cut|number[- ]two", 1.0),
    (r"(below|past) (the )?shoulder|ponytail|braid", 5.0),
    (r"waist", 7.0), (r"chin", 3.0), (r"shoulder|mid[- ]length|medium|\bbob\b", 4.0), (r"long", 6.0), (r"short", 2.0),
]

COLOR_FAMILIES = {
    "black": ["black", "pitch-black", "ebony"], "white": ["white", "cream", "off-white", "ivory", "snow-white"],
    "grey": ["grey", "gray", "charcoal", "silver", "slate", "ash", "heather"], "blue": ["blue", "navy", "cobalt", "teal", "sky-blue", "royal"],
    "red": ["red", "crimson", "scarlet", "maroon", "burgundy", "cherry"], "pink": ["pink", "rose", "magenta", "salmon"],
    "purple": ["purple", "violet", "lilac", "plum"], "orange": ["orange", "rust", "amber"], "yellow": ["yellow", "mustard", "lemon", "gold"],
    "green": ["green", "olive", "emerald", "forest-green"], "brown": ["brown", "chocolate"], "tan": ["tan", "beige", "khaki", "camel", "sand"],
}
COLOR_OF = {w: fam for fam, ws in COLOR_FAMILIES.items() for w in ws}
DARK_FAMILIES = ["black", "blue", "grey", "brown", "green", "purple"]   # what a bare "dark" could mean
# garment word -> (family, sub-type). Sub-types only differ where the difference is meaningful.
GARMENT = {}
for _w in ["jacket", "coat", "raincoat", "anorak", "windbreaker", "parka", "blazer", "poncho", "waterproof"]: GARMENT[_w] = ("outer", "outer")
for _w in ["sweater", "jumper", "pullover", "sweatshirt", "cardigan", "knitwear"]: GARMENT[_w] = ("knit", "sweater")
for _w in ["hoodie", "hooded", "fleece", "zip-up"]: GARMENT[_w] = ("knit", "hoodie")
for _w in ["shirt", "button-up", "blouse", "top", "polo"]: GARMENT[_w] = ("top", "shirt")
for _w in ["tee", "t-shirt", "tshirt", "crew-neck"]: GARMENT[_w] = ("top", "tee")
for _w in ["trousers", "pants", "slacks", "jeans", "denims", "chinos", "joggers", "bottoms", "leggings", "sweatpants"]: GARMENT[_w] = ("legwear", "legwear")
for _w in ["shorts", "cut-offs", "bermudas"]: GARMENT[_w] = ("shorts", "shorts")
GARMENT["skirt"] = ("skirt", "skirt")
for _w in ["dress", "frock", "gown", "sundress"]: GARMENT[_w] = ("dress", "dress")
for _w in ["cap", "hat", "beanie"]: GARMENT[_w] = ("headwear", "headwear")
for _w in ["scarf", "shawl", "stole", "headscarf", "dupatta"]: GARMENT[_w] = ("neckwear", "neckwear")
for _w in ["boots", "wellingtons", "gumboots"]: GARMENT[_w] = ("footwear", "boots")
for _w in ["trainers", "sneakers", "plimsolls"]: GARMENT[_w] = ("footwear", "sport")
for _w in ["sandals", "flip-flops", "slippers", "chappals"]: GARMENT[_w] = ("footwear", "open")
GARMENT["shoes"] = ("footwear", "shoes")
FAMILIES = sorted({v[0] for v in GARMENT.values()})
SUBS = sorted({v[1] for v in GARMENT.values()})
COLORS = sorted(COLOR_FAMILIES)

MARK_TYPES = [
    ("scar", r"scar|burn|gash|wound|cut mark"), ("burn", r"burn"),
    ("mole", r"\bmole|beauty spot|birthmark|\bspot\b|dark mark|\bpatch\b"),
    ("tattoo", r"tattoo|\bbird\b|\bink\b|inked"), ("piercing", r"pierc|\bstud\b|\bring\b"),
    ("glasses", r"glass|spectacle|rimmed|\bspecs\b"), ("mobility", r"limp|walking stick|\bcane\b|\bstick\b|favours|\bgait\b|drags|crutch|walking aid|unevenly"),
    ("tooth", r"toot|teeth|\bgap\b|incisor"),
]
MARK_LOCS = [
    ("face", r"cheek|eyebrow|brow\b|forehead|\beye\b|\bface\b|nose|nostril|\blip\b|\bchin\b"), ("neck", r"neck|throat"),
    ("hand", r"\bhand|finger"), ("arm", r"arm|wrist|elbow"), ("leg", r"\bleg|knee|ankle|foot"),
    ("ear", r"\bears?\b"),
]


def _txt(x):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return ""
    return str(x).strip().lower()


# ----------------------------------------------------------------------------- parsers
def parse_hair(s):
    s = _txt(s)
    color = next((v for rx, v in HAIR_COLOR if re.search(rx, s)), np.nan)
    length = next((v for rx, v in HAIR_LEN if re.search(rx, s)), np.nan)
    return color, length


def parse_clothing(s):
    """-> list of (color_family | 'dark' | None, garment_family, garment_sub)"""
    s = re.sub(r"-colou?red\b", "", _txt(s))
    items = []
    for chunk in re.split(r",|;|\band\b|&", s):
        toks = re.findall(r"[a-z]+(?:-[a-z]+)*", chunk)
        if not toks:
            continue
        color = next((COLOR_OF[t] for t in toks if t in COLOR_OF), None)
        if color is None and "dark" in toks:
            color = "dark"
        gs = [GARMENT[t] for t in toks if t in GARMENT]
        if "hooded" in toks or "zip-up" in toks:              # "hooded sweatshirt", "zip-up top" are one hoodie
            gs = [g for g in gs if g[0] not in ("knit", "top")] + [GARMENT["hoodie"]]
        for fam, sub in dict.fromkeys(gs):
            items.append((color, fam, sub))
    return items


def parse_marks(s):
    """-> list of (type, location, side) per distinguishing mark"""
    s = _txt(s)
    out = []
    for chunk in re.split(r";|\band\b", s):
        if not chunk.strip():
            continue
        types = [t for t, rx in MARK_TYPES if re.search(rx, chunk)]
        if not types and re.search(r"\bmark\b", chunk):
            types = ["mole"]
        loc = next((l for l, rx in MARK_LOCS if re.search(rx, chunk)), "")
        side = "left" if "left" in chunk else ("right" if "right" in chunk else "")
        for t in types:
            out.append((t, loc, side))
    return out


# ----------------------------------------------------------------------------- fitted artifacts
class Artifacts:
    """Things fitted once on the whole corpus (text statistics, places). No labels are used."""

    def __init__(self, places_df):
        self.places = places_df.reset_index(drop=True)
        self.place_names = [p.lower() for p in self.places["place"]]
        self.vec = {}

    def fit(self, missing_df, found_df):
        both = pd.concat([missing_df, found_df], ignore_index=True)
        def fit_char(col):
            texts = [_txt(x) for x in both[col] if _txt(x)]
            return TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, min_df=2).fit(texts)
        self.vec["hair"], self.vec["clothing"], self.vec["marks"] = fit_char("hair"), fit_char("clothing"), fit_char("marks")
        desc = [_txt(x) for x in both["description"]]
        self.vec["desc_word"] = TfidfVectorizer(sublinear_tf=True, ngram_range=(1, 2), min_df=2, stop_words="english").fit(desc)
        self.vec["desc_char"] = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, min_df=3).fit(desc)
        return self

    def place_index(self, name):
        n = _txt(name)
        if not n:
            return -1
        if n in self.place_names:
            return self.place_names.index(n)
        close = difflib.get_close_matches(n, self.place_names, n=1, cutoff=0.75)
        return self.place_names.index(close[0]) if close else -1


class Side:
    """All the per-record arrays for one list of records (reports or found people)."""
    pass


def _incidence(rows, vocab, weights=None):
    idx = {v: i for i, v in enumerate(vocab)}
    data, r, c = [], [], []
    for i, toks in enumerate(rows):
        for t, w in toks:
            if t in idx:
                r.append(i); c.append(idx[t]); data.append(w)
    m = sparse.csr_matrix((data, (r, c)), shape=(len(rows), len(vocab)), dtype=np.float32)
    return m


def build_side(df, kind, art):
    """kind is 'missing' or 'found'. Turns a DataFrame of records into a Side."""
    df = df.reset_index(drop=True)
    S = Side()
    S.n, S.ids = len(df), list(df["id"])
    S.age_min = df["age_min"].astype(float).to_numpy()
    S.age_max = df["age_max"].astype(float).to_numpy()
    S.gender = np.array([GENDER_CODE.get(_txt(g), 0) for g in df["gender"]])
    S.height = pd.to_numeric(df["height_cm"], errors="coerce").to_numpy(dtype=float)
    tcol, pcol = ("last_seen_time", "last_seen_place") if kind == "missing" else ("found_time", "found_place")
    # hours since 1970, computed as a Timedelta ratio so it does not depend on pandas' internal time resolution
    S.hours = ((pd.to_datetime(df[tcol]) - pd.Timestamp("1970-01-01")) / pd.Timedelta(hours=1)).to_numpy(dtype=float)
    pi = np.array([art.place_index(p) for p in df[pcol]])
    S.lat = np.where(pi >= 0, art.places["lat"].to_numpy()[np.maximum(pi, 0)], np.nan)
    S.lon = np.where(pi >= 0, art.places["lon"].to_numpy()[np.maximum(pi, 0)], np.nan)

    hp = [parse_hair(h) for h in df["hair"]]
    S.hair_color = np.array([c for c, _ in hp], dtype=float)
    S.hair_len = np.array([l for _, l in hp], dtype=float)

    def tf(col, key):
        texts = [_txt(x) for x in df[col]]
        return normalize(art.vec[key].transform(texts)), np.array([bool(t) for t in texts])
    S.hair_char, _ = tf("hair", "hair")
    S.cloth_char, _ = tf("clothing", "clothing")
    S.marks_char, S.marks_known = tf("marks", "marks")
    S.desc_word, _ = tf("description", "desc_word")
    S.desc_char, _ = tf("description", "desc_char")

    cl = [parse_clothing(c) for c in df["clothing"]]
    S.cloth_known = np.array([len(x) > 0 for x in cl])
    def cloth_rows(fn):
        return [fn(items) for items in cl]
    S.cloth_family = normalize(_incidence(cloth_rows(lambda it: [(f, 1.0) for _, f, _ in it]), FAMILIES))
    S.cloth_sub = normalize(_incidence(cloth_rows(lambda it: [(s, 1.0) for _, _, s in it]), SUBS))
    def colors(it):
        out = []
        for c, _, _ in it:
            if c == "dark":
                out += [(d, 0.35) for d in DARK_FAMILIES]
            elif c:
                out.append((c, 1.0))
        return out
    S.cloth_color = normalize(_incidence(cloth_rows(colors), COLORS))
    item_vocab = [f"{c}|{f}" for c in COLORS for f in FAMILIES]
    def items_tok(it):
        out = []
        for c, f, _ in it:
            if c == "dark":
                out += [(f"{d}|{f}", 0.35) for d in DARK_FAMILIES]
            elif c:
                out.append((f"{c}|{f}", 1.0))
        return out
    S.cloth_item = normalize(_incidence(cloth_rows(items_tok), item_vocab))

    mk = [parse_marks(m) for m in df["marks"]]
    types = [m[0] for m in MARK_TYPES]
    tl_vocab = [f"{t}|{l}" for t in types for l in [m[0] for m in MARK_LOCS] + [""]]
    S.marks_type = normalize(_incidence([[(t, 1.0) for t, _, _ in x] for x in mk], types))
    S.marks_typeloc = normalize(_incidence([[(f"{t}|{l}", 1.0) for t, l, _ in x if l] for x in mk], tl_vocab))
    S.marks_left = _incidence([[(f"{t}|{l}", 1.0) for t, l, s in x if s == "left"] for x in mk], tl_vocab)
    S.marks_right = _incidence([[(f"{t}|{l}", 1.0) for t, l, s in x if s == "right"] for x in mk], tl_vocab)
    S.marks_parsed = mk
    S.marks_known = S.marks_known  # raw text present
    return S


def _cos(A, B):
    return (A @ B.T).toarray().astype(np.float32)


def pair_tensor(M, F):
    """Features for every (missing i, found j): array of shape (M.n, F.n, len(FEATURES))."""
    nm, nf = M.n, F.n
    X = np.zeros((nm, nf, len(FEATURES)), dtype=np.float32)
    def put(name, a):
        X[:, :, COL[name]] = a

    gm, gf = M.gender[:, None], F.gender[None, :]
    both_mf = np.isin(gm, [1, 2]) & np.isin(gf, [1, 2])
    put("g_same", (gm == gf) & (gm != 0))
    put("g_conflict", both_mf & (gm != gf))
    put("g_unk", (gm == 0) | (gf == 0) | ((gm != gf) & ((gm == 3) | (gf == 3))))

    amin, amax = np.maximum(M.age_min[:, None], F.age_min[None, :]), np.minimum(M.age_max[:, None], F.age_max[None, :])
    ov = amax - amin
    put("age_overlap", ov >= 0)
    put("age_gap_norm", np.minimum(np.maximum(-ov, 0), 30) / 30)
    mid = np.abs((M.age_min + M.age_max)[:, None] / 2 - (F.age_min + F.age_max)[None, :] / 2)
    put("age_mid_diff_norm", np.minimum(mid, 40) / 40)
    put("age_child_adult_conflict", ((M.age_max[:, None] < 13) & (F.age_min[None, :] >= 18)) |
        ((F.age_max[None, :] < 13) & (M.age_min[:, None] >= 18)))

    hk = ~np.isnan(M.height)[:, None] & ~np.isnan(F.height)[None, :]
    put("h_known", hk)
    put("h_diff_norm", np.where(hk, np.minimum(np.abs(M.height[:, None] - F.height[None, :]), 40) / 40, 0))

    for name, a, b in (("hair_color", M.hair_color, F.hair_color), ("hair_len", M.hair_len, F.hair_len)):
        k = ~np.isnan(a)[:, None] & ~np.isnan(b)[None, :]
        put(name + "_known", k)
        put(name + "_sim", np.where(k, 1 - np.abs(a[:, None] - b[None, :]) / 7, 0))
    put("hair_char_sim", _cos(M.hair_char, F.hair_char))

    put("cloth_known", M.cloth_known[:, None] & F.cloth_known[None, :])
    put("cloth_family", _cos(M.cloth_family, F.cloth_family))
    put("cloth_sub", _cos(M.cloth_sub, F.cloth_sub))
    put("cloth_color", _cos(M.cloth_color, F.cloth_color))
    put("cloth_item", _cos(M.cloth_item, F.cloth_item))
    put("cloth_char_sim", _cos(M.cloth_char, F.cloth_char))

    put("marks_known", M.marks_known[:, None] & F.marks_known[None, :])
    put("marks_one_blank", M.marks_known[:, None] ^ F.marks_known[None, :])
    put("marks_type", _cos(M.marks_type, F.marks_type))
    put("marks_typeloc", _cos(M.marks_typeloc, F.marks_typeloc))
    same = _cos(M.marks_left, F.marks_left) + _cos(M.marks_right, F.marks_right)
    cross = _cos(M.marks_left, F.marks_right) + _cos(M.marks_right, F.marks_left)
    put("marks_side_match", np.minimum(same, 1))
    put("marks_side_conflict", np.clip(cross - same, 0, 1))
    put("marks_char_sim", _cos(M.marks_char, F.marks_char))

    put("desc_word_sim", _cos(M.desc_word, F.desc_word))
    put("desc_char_sim", _cos(M.desc_char, F.desc_char))

    pk = ~np.isnan(M.lat)[:, None] & ~np.isnan(F.lat)[None, :]
    la1, lo1, la2, lo2 = (np.radians(v) for v in (M.lat[:, None], M.lon[:, None], F.lat[None, :], F.lon[None, :]))
    h = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
    km = np.where(pk, 6371 * 2 * np.arcsin(np.sqrt(np.clip(h, 0, 1))), 0)
    gap = F.hours[None, :] - M.hours[:, None]
    speed = np.where(gap < 0, 60, np.minimum(km / np.maximum(gap, 0.25), 60))
    put("place_known", pk)
    put("km_norm", np.minimum(km, 20) / 20)
    put("gap_negative", gap < 0)
    put("speed_norm", np.where(pk, np.log1p(speed) / np.log1p(60), 0))
    return X


# ----------------------------------------------------------------------------- hand-weighted baseline
def rules_score(X):
    """Transparent hand-weighted baseline (weights set by hand, never fitted). X: (..., F) -> (...)"""
    g = lambda n: X[..., COL[n]]
    s = (1.0 * g("g_same") - 4.0 * g("g_conflict")
         + 1.5 * g("age_overlap") - 3.0 * g("age_gap_norm") - 1.5 * g("age_mid_diff_norm") - 3.0 * g("age_child_adult_conflict")
         - 2.5 * g("h_diff_norm")
         + 0.8 * (g("hair_color_sim") - 0.5 * g("hair_color_known")) + 0.5 * (g("hair_len_sim") - 0.5 * g("hair_len_known"))
         + 1.0 * g("cloth_family") + 0.5 * g("cloth_sub") + 1.0 * g("cloth_color") + 1.5 * g("cloth_item") + 0.8 * g("cloth_char_sim")
         + 1.0 * g("marks_type") + 1.5 * g("marks_typeloc") + 0.7 * g("marks_side_match") - 1.0 * g("marks_side_conflict") + 1.0 * g("marks_char_sim")
         + 1.5 * g("desc_word_sim") + 1.0 * g("desc_char_sim")
         - 4.0 * g("gap_negative") - 3.0 * g("speed_norm") - 0.3 * g("km_norm"))
    return s


# ----------------------------------------------------------------------------- human-readable reasons
def _rng(a, b):
    a, b = int(a), int(b)
    return f"{a}" if a == b else f"{a}-{b}"


def reasons(m, f, x):
    """m, f: dicts of the two records; x: feature vector (np array). -> list of {label, matched}"""
    g = lambda n: float(x[COL[n]])
    out = []
    gm, gf = _txt(m.get("gender")), _txt(f.get("gender"))
    if g("g_same"):
        out.append((f"Gender matches ({gm})", True))
    elif g("g_conflict"):
        out.append((f"Gender differs ({gm} vs {gf})", False))
    else:
        out.append(("Gender unclear in one record", False))
    ar = f"{_rng(m['age_min'], m['age_max'])} vs {_rng(f['age_min'], f['age_max'])}"
    if g("age_overlap"):
        out.append((f"Age ranges overlap ({ar}; found age is an estimate)", True))
    else:
        out.append((f"Age ranges do not overlap ({ar})", g("age_gap_norm") * 30 <= 4))
    if g("h_known"):
        d = abs(float(m["height_cm"]) - float(f["height_cm"]))
        out.append((f"Height {int(float(m['height_cm']))} cm vs {int(float(f['height_cm']))} cm", d <= 8))
    if g("hair_color_known") or g("hair_len_known"):
        # three levels, so the tick agrees with the score: a tick only for a real match, a dash for a partial one
        c, l = (g("hair_color_sim") if g("hair_color_known") else 1.0), (g("hair_len_sim") if g("hair_len_known") else 1.0)
        word, ok = ("similar", True) if (c >= 0.75 and l >= 0.85) else (("partly similar", False) if (c >= 0.5 and l >= 0.5) else ("differs", False))
        out.append((f"Hair {word} ({_txt(m.get('hair'))} vs {_txt(f.get('hair'))})", ok))
    if g("cloth_known"):
        if g("cloth_item") >= 0.3:
            word, ok = "overlaps", True
        elif g("cloth_family") >= 0.5:
            word, ok = "only partly overlaps (same kinds of garment, different colours or items)", False
        else:
            word, ok = "differs", False
        out.append((f"Clothing {word} ({_txt(m.get('clothing'))} vs {_txt(f.get('clothing'))})", ok))
    if g("marks_known"):
        if g("marks_side_conflict") > 0:
            out.append((f"Same kind of mark but on opposite sides ({_txt(m.get('marks'))} vs {_txt(f.get('marks'))})", False))
        else:
            ok = g("marks_typeloc") >= 0.3 or g("marks_type") >= 0.5
            out.append((f"Distinguishing marks {'in both' if ok else 'differ'} ({_txt(m.get('marks'))} vs {_txt(f.get('marks'))})", ok))
    elif g("marks_one_blank"):
        out.append(("Distinguishing marks recorded in only one record", False))
    if g("place_known") or g("gap_negative"):
        km = g("km_norm") * 20
        gap = (pd.Timestamp(f["found_time"]) - pd.Timestamp(m["last_seen_time"])).total_seconds() / 3600
        if g("gap_negative"):
            out.append(("Found before the person was last seen (not plausible)", False))
        else:
            out.append((f"Found {km:.0f} km from last seen place, {gap:.0f} hours later", g("speed_norm") < 0.45))
    return [{"label": l, "matched": bool(ok)} for l, ok in out]
