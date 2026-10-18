"""Task 3: a harder version of the dataset, to check the matcher's hand-written normalisation isn't tuned to make_data.py.
Same people logic, same sizes, same checks, but NEW vocabulary and wording on both sides
(words the normaliser has never seen), extra formats ("jacket (red)", "blk", "approx"), and more typos.

  python make_data_hard.py          -> shared/data_hard/{places,missing,found,truth}.csv
"""
import os, random
import numpy as np
import make_data as md

random.seed(43); np.random.seed(43)
md.OUT_DIR = os.path.join("shared", "data_hard")

# ------------------------------------------------------------------ new wording (same meanings, same keys)
md.HAIR_COLOR = {
    "black": ["raven", "jet", "very dark"], "dark brown": ["deep brown", "espresso", "near-black"],
    "brown": ["brunette", "medium brown", "mousy brown"], "light brown": ["dirty blonde", "honey", "light chestnut"],
    "blonde": ["golden", "platinum", "flaxen"], "grey": ["greying", "ash grey", "pepper-grey"],
    "white": ["silver-white", "completely white", "pure white"], "red": ["copper", "reddish", "titian"],
}
md.HAIR_LENGTH = {
    "very short": ["shaved", "crew cut", "number-two cut"], "short": ["cropped short", "above the ears", "pixie"],
    "medium": ["mid-length", "to the shoulders", "bob-length"], "long": ["past the shoulders", "in a long braid", "ponytail"],
}
md.COLORS = {
    "red": ["maroon", "burgundy", "cherry"], "blue": ["sky-blue", "royal blue", "teal"], "green": ["khaki", "emerald", "forest-green"],
    "yellow": ["lemon", "gold"], "black": ["pitch-black", "ebony"], "white": ["ivory", "snow-white"], "grey": ["slate", "ash", "heather"],
    "brown": ["chocolate", "camel"], "pink": ["magenta", "salmon"], "purple": ["lilac", "plum"], "orange": ["rust", "amber"],
}
md.GARMENTS = {
    "jacket": ["windbreaker", "parka", "blazer"], "jeans": ["denims", "jean trousers"], "t-shirt": ["top", "vest top", "crew-neck"],
    "shirt": ["blouse", "collared shirt", "polo"], "dress": ["gown", "sundress"], "skirt": ["long skirt", "pleated skirt"],
    "hoodie": ["fleece", "zip-up top"], "sweater": ["cardigan", "knitwear"], "trousers": ["chinos", "joggers", "tracksuit bottoms"],
    "shorts": ["cut-offs", "bermudas"], "raincoat": ["poncho", "waterproof"], "scarf": ["headscarf", "dupatta"],
    "cap": ["beanie", "sun hat"], "sneakers": ["canvas shoes", "plimsolls"], "sandals": ["slippers", "chappals"], "boots": ["gumboots", "work boots"],
}
md.MARKS = {
    "scar_eyebrow": ("cut mark through {side} brow", ["healed gash by {side} eyebrow", "forehead scar", "old wound above {side} eye"]),
    "mole_cheek": ("dark spot on {side} cheek", ["raised mole, {side} side of face", "mole on the face"]),
    "tattoo_forearm": ("inked bird on {side} forearm", ["swallow tattoo, {side} arm", "ink on forearm"]),
    "front_tooth": ("gap where a front tooth should be", ["broken incisor", "tooth missing at the front"]),
    "birthmark_neck": ("port-wine mark on neck", ["stain-like birthmark on throat", "neck birthmark"]),
    "glasses": ("specs", ["wire-frame glasses", "reading glasses on a cord"]),
    "limp": ("drags {side} leg", ["uneven gait, {side} side", "walks unevenly"]),
    "burn_hand": ("old burn on {side} hand", ["shiny burn scar, {side} hand", "burned hand"]),
    "nose_piercing": ("nose ring", ["stud in the nose", "pierced nostril"]),
    "walking_stick": ("walks with a cane", ["needs a walking aid", "uses a crutch"]),
}
md.SIDED = {k for k, (t, _) in md.MARKS.items() if "{side}" in t}

# ------------------------------------------------------------------ new formats + extra noise
_orig_item = md.item_text
def item_text(color, garment):
    c, g = md.say(md.COLORS[color]), md.say(md.GARMENTS[garment])
    return random.choice([f"{c} {g}", f"{g} ({c})", f"{g} in {c}", f"{c}-coloured {g}"])
md.item_text = item_text

ABBREV = [("approximately", "approx"), ("approx.", "~"), ("years", "yrs"), ("black", "blk"), ("light", "lt"), ("with", "w/"),
          ("hospital", "hosp."), ("about", "abt"), ("wearing", "wearing:")]
def noisify(text):
    t = text
    for long, short in ABBREV:
        if long in t and random.random() < .35:
            t = t.replace(long, short)
    if random.random() < .15:
        t = t.lower()
    if random.random() < .25:
        t = md.add_typos(t, n=3)
    return t

_orig_missing, _orig_found = md.missing_record, md.found_record
def missing_record(p, mid):
    r = _orig_missing(p, mid); r["description"] = noisify(r["description"]); return r
def found_record(p, fid, implausible=False):
    r = _orig_found(p, fid, implausible); r["description"] = noisify(r["description"]); return r
md.missing_record, md.found_record = missing_record, found_record

if __name__ == "__main__":
    md.main()
