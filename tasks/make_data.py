#!/usr/bin/env python3
"""
make_data.py - synthetic dataset for the missing-person matching demo.

Everything here is FICTIONAL: the city, the places, the people, the phone numbers.
Run from the repo root:   python make_data.py
Writes four CSV files (UTF-8, header row) into shared/data/:
    places.csv   place, lat, lon
    missing.csv  family reports (400)
    found.csv    records from authorities (600)
    truth.csv    the 300 true missing -> found pairs (for evaluation only)

Uses only the standard library + pandas + numpy. Fixed seed, so every run gives the same data.
Teammates: the vocabulary lists near the top are safe to edit.
"""
import math
import os
import random
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

random.seed(42)
np.random.seed(42)

OUT_DIR = os.path.join("shared", "data")

N_MISSING = 400
N_FOUND = 600
N_PAIRS = 300                 # true pairs; 100 missing people stay unmatched
DECOY_PAIR_SHARE = 0.30       # share of true pairs that also get 1-3 look-alike found records

# =============================================================================
# 1. PLACES - one fictional flood-affected city ("Lower Harrow"), ~15 km across
# =============================================================================
CITY_CENTER = (47.2000, 9.6000)   # fictional coordinates, used only to compute distances
PLACES = [
    # (name, km east of centre, km north of centre)
    ("Old Grain Market", 0.4, 0.3),
    ("Fish Market", 2.8, -1.9),
    ("Ferry Bridge", 1.6, -0.8),
    ("Canal Street Bridge", -1.2, 0.9),
    ("Iron Bridge", 4.9, 2.2),
    ("Central Bus Station", 0.0, -0.4),
    ("Mill Road Bus Stop", -3.1, -2.6),
    ("North Gate Bus Stop", -0.6, 5.4),
    ("Riverside Primary School", 2.1, 1.4),
    ("Hillcrest High School", -4.2, 3.6),
    ("Willow Lane", -2.4, -0.9),
    ("Brickworks Road", 5.6, -3.4),
    ("Textile Mill Colony", -5.8, -4.7),
    ("East Embankment", 6.3, 0.5),
    ("Water Tower Square", -1.5, 2.7),
    ("Railway Station", 1.0, 3.9),
    ("Lakeside Park", -6.6, 1.8),
    ("Harbour Quay", 3.8, -5.6),
    ("Stadium Shelter", 3.3, 2.9),
    ("Community Hall Shelter", -2.0, 1.6),
    ("Hillcrest School Shelter", -4.4, 3.3),
    ("Civic Centre Shelter", 0.6, -2.2),
    ("Lower Harrow General Hospital", 1.3, 0.8),
    ("St. Brennan's Hospital", -3.5, -1.8),
    ("Field Hospital (Stadium Grounds)", 3.6, 3.2),
]
KM_PER_DEG_LAT = 111.0
KM_PER_DEG_LON = 111.0 * math.cos(math.radians(CITY_CENTER[0]))
PLACE_COORDS = {name: (round(CITY_CENTER[0] + n / KM_PER_DEG_LAT, 5), round(CITY_CENTER[1] + e / KM_PER_DEG_LON, 5)) for name, e, n in PLACES}
PLACE_KM = {name: (e, n) for name, e, n in PLACES}
CARE_PLACES = [p for p in PLACE_KM if "Shelter" in p or "Hospital" in p]      # valid current_location values
STREET_PLACES = [p for p in PLACE_KM if p not in CARE_PLACES]                 # where people go missing

def dist_km(a, b):
    (e1, n1), (e2, n2) = PLACE_KM[a], PLACE_KM[b]
    return math.hypot(e1 - e2, n1 - n2)

# =============================================================================
# 2. VOCABULARY (edit freely). Each entry: canonical key -> list of ways to say it.
# =============================================================================
HAIR_COLOR = {
    "black": ["black", "jet black", "dark"],
    "dark brown": ["dark brown", "black", "dark"],          # families and officials often disagree here
    "brown": ["brown", "mid brown", "chestnut"],
    "light brown": ["light brown", "dark blonde", "sandy"],
    "blonde": ["blonde", "fair", "light"],
    "grey": ["grey", "gray", "silver", "salt-and-pepper"],
    "white": ["white", "snow white", "grey-white"],
    "red": ["red", "auburn", "ginger"],
}
HAIR_LENGTH = {
    "very short": ["very short", "cropped", "buzz cut"],
    "short": ["short", "close-cut"],
    "medium": ["shoulder length", "medium length", "chin length"],
    "long": ["long", "waist length", "below the shoulders"],
}
COLORS = {
    "red": ["red", "crimson", "scarlet"], "blue": ["blue", "navy"], "green": ["green", "olive"],
    "yellow": ["yellow", "mustard"], "black": ["black", "dark"], "white": ["white", "cream", "off-white"],
    "grey": ["grey", "gray", "charcoal"], "brown": ["brown", "tan"], "pink": ["pink", "rose"],
    "purple": ["purple", "violet"], "orange": ["orange", "bright orange"],
}
GARMENTS = {
    "jacket": ["jacket", "coat", "anorak"], "jeans": ["jeans", "denim trousers"], "t-shirt": ["t-shirt", "tee"],
    "shirt": ["shirt", "button-up shirt"], "dress": ["dress", "frock"], "skirt": ["skirt"],
    "hoodie": ["hoodie", "hooded sweatshirt"], "sweater": ["sweater", "jumper", "pullover"],
    "trousers": ["trousers", "pants", "slacks"], "shorts": ["shorts"], "raincoat": ["raincoat", "rain jacket"],
    "scarf": ["scarf", "shawl"], "cap": ["cap", "baseball cap"], "sneakers": ["sneakers", "trainers", "running shoes"],
    "sandals": ["sandals", "flip-flops"], "boots": ["boots", "rubber boots", "wellingtons"],
}
TOPS = ["jacket", "t-shirt", "shirt", "hoodie", "sweater", "raincoat", "dress"]
BOTTOMS = ["jeans", "trousers", "shorts", "skirt"]
EXTRAS = ["scarf", "cap", "sneakers", "sandals", "boots"]

# Marks: (template with optional {side}, [other ways to say the same thing]); {side} = left/right
MARKS = {
    "scar_eyebrow": ("scar above {side} eyebrow", ["scar on forehead", "scar over {side} eye", "small scar near {side} brow"]),
    "mole_cheek": ("mole on {side} cheek", ["dark mole on {side} cheek", "beauty spot on face", "mole on face"]),
    "tattoo_forearm": ("tattoo of a bird on {side} forearm", ["bird tattoo on {side} arm", "small tattoo on forearm", "tattoo on {side} arm"]),
    "front_tooth": ("missing front tooth", ["gap in front teeth", "front tooth missing", "chipped front tooth"]),
    "birthmark_neck": ("birthmark on neck", ["brown patch on neck", "birthmark below ear", "dark mark on neck"]),
    "glasses": ("wears glasses", ["spectacles", "thick-rimmed glasses", "was wearing glasses"]),
    "limp": ("limp in {side} leg", ["walks with a limp", "favours {side} leg", "limping"]),
    "burn_hand": ("burn scar on {side} hand", ["old burn mark on {side} hand", "scarred {side} hand", "burn scar on hand"]),
    "nose_piercing": ("nose piercing", ["small nose stud", "pierced nose", "nose ring"]),
    "walking_stick": ("uses a walking stick", ["uses a cane", "walks with a stick", "had a walking cane"]),
}
SIDED = {k for k, (t, _) in MARKS.items() if "{side}" in t}

FIRST_SENTENCE_RELATION = {  # how a family member refers to the person (by age group and gender)
    ("child", "female"): ["My daughter", "Our little girl", "My niece", "My granddaughter"],
    ("child", "male"): ["My son", "Our little boy", "My nephew", "My grandson"],
    ("adult", "female"): ["My sister", "My wife", "My mother", "My cousin"],
    ("adult", "male"): ["My brother", "My husband", "My father", "My cousin"],
    ("elderly", "female"): ["My grandmother", "My mother", "Our neighbour's mother", "My aunt"],
    ("elderly", "male"): ["My grandfather", "My father", "My uncle", "Our elderly neighbour"],
}

# =============================================================================
# 3. HELPERS
# =============================================================================
pick = random.choice

def age_group(age):
    return "child" if age < 18 else "elderly" if age >= 65 else "adult"

def say(options):
    """Pick a wording."""
    return pick(options)

def item_text(color, garment):
    return f"{say(COLORS[color])} {say(GARMENTS[garment])}"

def mark_text(key, side, reword):
    canon, alts = MARKS[key]
    t = pick(alts) if reword else canon
    return t.replace("{side}", side)

def typo(word):
    if len(word) < 4 or not word.isalpha():
        return word
    i = random.randint(1, len(word) - 2)
    kind = pick(["swap", "drop", "double"])
    if kind == "swap":
        return word[:i] + word[i + 1] + word[i] + word[i + 2:]
    if kind == "drop":
        return word[:i] + word[i + 1:]
    return word[:i] + word[i] + word[i:]

def add_typos(text, n=2):
    words = text.split(" ")
    idx = [i for i, w in enumerate(words) if len(w.strip(".,")) >= 4 and w.strip(".,").isalpha()]
    for i in random.sample(idx, min(n, len(idx))):
        w = words[i]; core = w.strip(".,"); words[i] = w.replace(core, typo(core))
    return " ".join(words)

def fake_phone():
    return f"(555) {random.randint(200, 999)}-{random.randint(1000, 9999)}"   # 555 = fictional range

def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M")

# =============================================================================
# 4. PEOPLE (the hidden truth behind the records)
# =============================================================================
DISASTER_START = datetime(2026, 10, 14, 6, 0)

def make_person():
    r = random.random()
    age = random.randint(2, 17) if r < .22 else random.randint(65, 90) if r > .82 else random.randint(18, 64)
    gender = random.choices(["female", "male", "other"], weights=[49, 49, 2])[0]
    sex_for_body = gender if gender != "other" else pick(["female", "male"])
    if age < 13:
        height = int(85 + 6.2 * (age - 2) + random.gauss(0, 4))
    elif age < 18:
        height = int((158 if sex_for_body == "female" else 166) + random.gauss(0, 6))
    else:
        height = int((163 if sex_for_body == "female" else 176) + random.gauss(0, 7) - (4 if age >= 75 else 0))
    if age >= 65:
        color = random.choices(["grey", "white", "dark brown", "black"], weights=[45, 30, 15, 10])[0]
    elif age < 13:
        color = random.choices(["black", "dark brown", "brown", "light brown", "blonde", "red"], weights=[30, 25, 20, 10, 10, 5])[0]
    else:
        color = random.choices(list(HAIR_COLOR), weights=[25, 22, 18, 10, 8, 5, 2, 4])[0]
    length = random.choices(list(HAIR_LENGTH), weights=[15, 35, 30, 20] if sex_for_body == "female" else [35, 50, 10, 5])[0]
    bald = sex_for_body == "male" and age >= 50 and random.random() < .25
    top = pick([g for g in TOPS if not (g == "dress" and sex_for_body == "male")])
    outfit = [(pick(list(COLORS)), top)]
    if top != "dress":
        outfit.append((pick(["blue", "black", "grey", "brown"]), pick([b for b in BOTTOMS if not (b == "skirt" and sex_for_body == "male")])))
    if random.random() < .6:
        outfit.append((pick(list(COLORS)), pick(EXTRAS)))
    pool = [k for k in MARKS if not (k == "walking_stick" and age < 60) and not (k == "tattoo_forearm" and age < 16)]
    marks = [(k, pick(["left", "right"])) for k in random.sample(pool, k=random.choices([0, 1, 2], weights=[35, 45, 20])[0])]
    place = pick(STREET_PLACES)
    seen = DISASTER_START + timedelta(minutes=random.randint(0, 3 * 24 * 60))   # reports span ~3 days
    return dict(age=age, gender=gender, height=height, hair=(color, length, bald), outfit=outfit, marks=marks, place=place, seen=seen)

# =============================================================================
# 5. MISSING REPORT (family's view: tight age, own wording)
# =============================================================================
def missing_record(p, mid):
    a = p["age"]
    if a < 13:
        lo, hi = a, a + random.choice([0, 1])
    else:
        w = random.choice([1, 2, 2, 3])
        lo, hi = a - random.randint(0, w), a + random.randint(0, w)
    height = "" if random.random() < .2 else p["height"] + random.choice([-3, -2, 0, 0, 2, 3])
    color, length, bald = p["hair"]
    hair = "" if random.random() < .2 else ("bald" if bald else f"{HAIR_LENGTH[length][0]} {HAIR_COLOR[color][0]} hair")
    clothing = ", ".join(item_text(c, g) for c, g in p["outfit"])
    marks = "; ".join(mark_text(k, s, reword=False) for k, s in p["marks"])
    gender = p["gender"] if random.random() > .01 else "unknown"
    rel = pick(FIRST_SENTENCE_RELATION[(age_group(a), p["gender"] if p["gender"] in ("female", "male") else pick(["female", "male"]))])
    age_txt = f"{a}" if lo == hi else pick([f"about {round((lo + hi) / 2)}", f"{lo}-{hi}", f"around {round((lo + hi) / 2)}"])
    when = p["seen"].strftime("%A %I %p").replace(" 0", " ")
    templates = [
        f"{rel}, {age_txt}, was last seen near {p['place']} on {when}, wearing {clothing}.",
        f"Please help. {rel} ({age_txt}) went missing around {p['place']}. Last seen in {clothing}.",
        f"We are looking for {rel[0].lower() + rel[1:]}, {age_txt} years old. We lost each other at {p['place']} when the water rose.",
        f"{rel} has not come home. Age {age_txt}, last seen at {p['place']} on {when}.",
    ]
    desc = pick(templates)
    if hair == "bald":
        desc += " Bald."
    elif hair:
        desc += f" {pick(['Has', 'With'])} {hair}."
    if marks:
        desc += f" {pick(['Distinguishing marks:', 'You can recognise them by', 'Look for'])} {marks}."
    if random.random() < .3:
        desc += " " + pick(["Any information please call.", "We are very worried.", "They may be confused and scared."])
    if random.random() < .10:
        desc = add_typos(desc)
    return {"id": mid, "age_min": max(0, lo), "age_max": hi, "gender": gender, "height_cm": height, "hair": hair, "clothing": clothing,
            "marks": marks, "last_seen_place": p["place"], "last_seen_time": iso(p["seen"]), "description": desc, "contact": fake_phone(),
            "split": "dev"}

# =============================================================================
# 6. FOUND RECORD (authority's view: estimated age, different wording, people change clothes)
# =============================================================================
def found_age(a):
    r = random.random()
    if r < .4:                         # widened estimate
        lo, hi = a - random.randint(3, 8), a + random.randint(0, 5)
    elif r < .75:                      # shifted estimate
        d = random.choice([-1, 1]) * random.randint(3, 8)
        lo, hi = a + d - 2, a + d + 3
    else:                              # 10-year span ("aged 30-40")
        base = (a + random.randint(-4, 4)) // 5 * 5
        lo, hi = base - 5, base + 5
    if a < 18:                         # children are easier to age
        lo, hi = max(1, a - random.randint(1, 3)), a + random.randint(1, 3)
    lo = max(0, lo)
    return lo, max(lo + 1, hi)

def found_clothing(outfit, gender):
    bottoms = [b for b in BOTTOMS if not (b == "skirt" and gender == "male")]
    r = random.random()
    if r < .30:      # identical items (reworded)
        items = list(outfit)
    elif r < .70:    # partial overlap: keep one item, change the rest
        keep = pick(outfit)
        items = [keep] + [(pick(list(COLORS)), pick(EXTRAS + ["jacket", "raincoat", "sweater"])) for _ in range(random.randint(0, 1))]
    else:            # completely different (changed clothes, blanket, donated clothes)
        items = [(pick(list(COLORS)), pick(["raincoat", "sweater", "t-shirt", "hoodie", "jacket"])), (pick(list(COLORS)), pick(bottoms))]
    return ", ".join(item_text(c, g) for c, g in items)

def found_marks(marks):
    out = []
    for k, side in marks:
        r = random.random()
        if r < .20:
            continue                                        # blank on the found side
        if r < .30 and k in SIDED:
            out.append(mark_text(k, "right" if side == "left" else "left", reword=random.random() < .5))  # wrong side
        elif r < .80:
            out.append(mark_text(k, side, reword=True))     # same meaning, different words
        else:
            out.append(mark_text(k, side, reword=False))    # same words
    return "; ".join(out)

def nearby_place(origin, implausible=False):
    candidates = [q for q in STREET_PLACES if q != origin]   # people are found out in the city, then taken to care
    if implausible:
        far = sorted(candidates, key=lambda q: -dist_km(origin, q))[:5]
        return pick(far)
    weights = [math.exp(-dist_km(origin, q) / 2.5) for q in candidates]   # usually walking / short drive
    return random.choices(candidates, weights=weights)[0]

def found_record(p, fid, implausible=False):
    lo, hi = found_age(p["age"])
    height = "" if random.random() < .2 else p["height"] + random.choice([-1, 1]) * random.randint(5, 10)
    color, length, bald = p["hair"]
    hair = "" if random.random() < .2 else ("bald" if bald else f"{pick(HAIR_LENGTH[length])} {pick(HAIR_COLOR[color])}")
    gender = p["gender"]
    if random.random() < .03:
        gender = pick(["unknown", "female" if gender == "male" else "male"])
    clothing = found_clothing(p["outfit"], p["gender"])
    marks = found_marks(p["marks"])
    place = nearby_place(p["place"], implausible)
    hours = random.uniform(1, 2) if implausible else random.uniform(1, 72)
    t = p["seen"] + timedelta(hours=hours)
    care = min(CARE_PLACES, key=lambda c: dist_km(place, c)) if random.random() < .6 else pick(CARE_PLACES)
    who = {"female": ["female", "woman"], "male": ["male", "man"]}.get(gender, ["person", "individual"])
    grp = "child" if hi < 18 else "elderly" if lo >= 62 else "adult"
    noun = {"child": f"{who[0]} child", "elderly": f"elderly {who[1]}", "adult": f"adult {who[0]}"}[grp]
    templates = [
        f"{noun.capitalize()}, approx. {lo}-{hi} years, found at {place}, wearing {clothing}.",
        f"Unidentified {noun}, estimated age {lo}-{hi}. Brought in from {place}. Clothing: {clothing}.",
        f"{noun.capitalize()} located near {place} by rescue team, est. {lo}-{hi} yrs. Wearing {clothing}.",
        f"Registered at {care}: {noun}, age approx. {lo}-{hi}, found at {place}. Clothes: {clothing}.",
    ]
    desc = pick(templates)
    if height:
        desc += f" Height approx. {height} cm."
    if hair:
        desc += f" Hair: {hair}."
    if marks:
        desc += f" {marks[0].upper() + marks[1:]}."
    if random.random() < .35:
        desc += " " + pick(["Cannot give name.", "Disoriented, minor injuries.", "Speaks little, appears in shock.", "Stable condition.", "Asking for family."])
    if random.random() < .10:
        desc = add_typos(desc)
    return {"id": fid, "age_min": lo, "age_max": hi, "gender": gender, "height_cm": height, "hair": hair, "clothing": clothing, "marks": marks,
            "found_place": place, "found_time": iso(t), "current_location": care, "description": desc}

def decoy_of(p):
    """A different person who looks like p: same gender, overlapping age, similar clothing, nearby."""
    q = make_person()
    q["gender"] = p["gender"]
    q["age"] = max(1, p["age"] + random.randint(-4, 4)) if p["age"] >= 18 else max(2, p["age"] + random.randint(-2, 2))
    q["outfit"] = [pick(p["outfit"])] + q["outfit"][1:]                     # shares at least one item
    if random.random() < .5:
        q["hair"] = p["hair"]
    q["place"] = nearby_place(p["place"])
    q["seen"] = p["seen"] + timedelta(hours=random.uniform(-6, 6))
    return q

# =============================================================================
# 7. BUILD
# =============================================================================
def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    people = [make_person() for _ in range(N_MISSING)]
    missing = [missing_record(p, f"M{i + 1}") for i, p in enumerate(people)]
    for r in random.sample(missing, int(N_MISSING * .4)):
        r["split"] = "test"                                                 # 60% dev, 40% test

    matched = random.sample(range(N_MISSING), N_PAIRS)
    implausible = set(random.sample(matched, round(N_PAIRS * .05)))         # ~5% hard cases
    found_people = [(people[i], i, i in implausible) for i in matched]

    # decoys for ~30% of true pairs (1-3 each), then fill to 600 with people nobody reported
    decoys = []
    for i in random.sample(matched, round(N_PAIRS * DECOY_PAIR_SHARE)):
        for _ in range(random.randint(1, 3)):
            if len(decoys) < N_FOUND - N_PAIRS:
                decoys.append(decoy_of(people[i]))
    strangers = [make_person() for _ in range(N_FOUND - N_PAIRS - len(decoys))]
    rows = [(p, i, imp) for p, i, imp in found_people] + [(q, None, False) for q in decoys + strangers]
    random.shuffle(rows)                                                    # so F-ids don't reveal which are matches

    found, truth = [], []
    for k, (p, mi, imp) in enumerate(rows):
        fid = f"F{k + 1}"
        found.append(found_record(p, fid, imp))
        if mi is not None:
            truth.append({"missing_id": missing[mi]["id"], "found_id": fid})

    places = pd.DataFrame([{"place": n, "lat": PLACE_COORDS[n][0], "lon": PLACE_COORDS[n][1]} for n, _, _ in PLACES])
    dm, df, dt = pd.DataFrame(missing), pd.DataFrame(found), pd.DataFrame(truth)
    places.to_csv(os.path.join(OUT_DIR, "places.csv"), index=False, encoding="utf-8")
    dm.to_csv(os.path.join(OUT_DIR, "missing.csv"), index=False, encoding="utf-8")
    df.to_csv(os.path.join(OUT_DIR, "found.csv"), index=False, encoding="utf-8")
    dt.to_csv(os.path.join(OUT_DIR, "truth.csv"), index=False, encoding="utf-8")

    # =========================================================================
    # 8. CHECKS
    # =========================================================================
    print("=== Row counts ===")
    for name, d in (("places", places), ("missing", dm), ("found", df), ("truth", dt)):
        print(f"  {name}.csv: {len(d)}")
    print("  split:", dm["split"].value_counts().to_dict())
    print(f"  decoy (look-alike) found records: {len(decoys)} | unreported strangers: {len(strangers)} | implausible true pairs: {len(implausible)}")

    print("\n=== Blank values per column ===")
    for name, d in (("missing", dm), ("found", df)):
        blanks = (d.replace("", np.nan).isna()).sum()
        print(f"  {name}:", {c: int(v) for c, v in blanks.items() if v})
    required_m = ["id", "age_min", "age_max", "gender", "description", "last_seen_place", "last_seen_time", "contact", "split"]
    required_f = ["id", "age_min", "age_max", "gender", "description", "found_place", "found_time", "current_location"]
    assert not dm[required_m].replace("", np.nan).isna().any().any(), "blank in a required missing.csv column"
    assert not df[required_f].replace("", np.nan).isna().any().any(), "blank in a required found.csv column"
    print("  required columns have no blanks: OK")

    print("\n=== Ground truth integrity ===")
    assert dt["missing_id"].isin(dm["id"]).all() and dt["found_id"].isin(df["id"]).all(), "truth.csv has unknown IDs"
    assert dt["found_id"].is_unique, "a found record is paired twice"
    assert dt["missing_id"].is_unique, "a missing report is paired twice"
    assert set(df["current_location"]) <= set(CARE_PLACES), "current_location must be a shelter or hospital"
    gaps = [(datetime.fromisoformat(f) - datetime.fromisoformat(m)).total_seconds() / 3600
            for m, f in zip(dm.set_index("id").loc[dt["missing_id"], "last_seen_time"], df.set_index("id").loc[dt["found_id"], "found_time"])]
    assert all(1 <= g <= 72 for g in gaps), "found_time must be 1-72 hours after last_seen_time"
    print(f"  all {len(dt)} pairs point to real IDs, no found ID used twice, found 1-72 h after last seen: OK")

    print("\n=== Five true pairs, side by side ===")
    cols = ["age_min", "age_max", "gender", "height_cm", "hair", "clothing", "marks", "description"]
    for _, row in dt.sample(5, random_state=1).iterrows():
        m = dm.set_index("id").loc[row["missing_id"]]
        f = df.set_index("id").loc[row["found_id"]]
        side = pd.DataFrame({f"MISSING {row['missing_id']}": [m[c] for c in cols] + [f"{m['last_seen_place']} @ {m['last_seen_time']}"],
                             f"FOUND {row['found_id']}": [f[c] for c in cols] + [f"{f['found_place']} @ {f['found_time']}"]},
                            index=cols + ["place / time"])
        with pd.option_context("display.max_colwidth", 70, "display.width", 200):
            print(side.to_string(), "\n")
    print(f"Done. Files written to {OUT_DIR}/")

if __name__ == "__main__":
    main()
