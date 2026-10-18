"""
extract.py - fills in hair, clothing and distinguishing marks from the free-text description when the form boxes
were left empty (a worried family member often types one paragraph and nothing else).

Two layers, based on Aneeza's experiments:
  1. regex  - instant, always on. Uses the same word lists as features.py, and only ever copies words that are
              really in the text, so it cannot invent anything.
  2. Granite 350M (optional, REUNITE_GRANITE=1) - a small language model that reads the text and returns JSON.
              It runs on the IBM Z AI accelerator through PyTorch (torch.device("nnpa")) when that is available.
              Every answer passes a GROUNDING CHECK: an item that is not (nearly) word-for-word in the report is
              thrown away. (Granite once copied "navy coat, grey slacks" out of its own prompt example.)

Anything filled in this way is recorded in the record's "auto_filled" field, so the authority can see which
details were read from the text and which were typed into a box.

Granite loads in the background, so the app starts at once and works with regex only until it is ready.
"""
import difflib
import json
import os
import re
import threading
import time

import pandas as pd

import features as FT

HAIR_WORDS_SKIP = {"she", "he", "they", "has", "had", "have", "with", "w/", "and", "a", "the", "his", "her", "their",
                   "is", "was", "wearing", "who"}
HAIR_PATTERNS = [
    re.compile(r"\bhair\s*[:\-]\s*([^.;\n]{2,40})", re.I),
    re.compile(r"\b(?:has|had|with|w/)\s+([^.;,]{2,40}?)\s+hair\b", re.I),
    re.compile(r"([A-Za-z\-]+(?:\s[A-Za-z\-]+){0,3})\s+hair\b", re.I),
]
CLOTHING_CLAUSE = re.compile(r"(?:wearing:?|clothing:|clothes:|last seen in|dressed in)\s+([^.;]+)", re.I)
MARK_LABEL = re.compile(r"^(?:distinguishing marks?|identifying marks?|marks?|you can recognise them by|look for|"
                        r"has|with|wears|wearing)\s*[:\-]?\s+", re.I)
NOT_A_MARK = re.compile(r"\b(?:wearing|clothes|clothing|hair|height|last seen|found at|looking for|registered|lost each|"
                        r"went missing|not come home|worried|confused|please)\b", re.I)
WORD = re.compile(r"[a-z]+(?:-[a-z]+)*")


def _empty(v):
    return v is None or (isinstance(v, float) and v != v)


def _fix_hair_word(text):
    """'hari' or 'hiar' -> 'hair'"""
    return re.sub(r"\bh[a-z]{2,4}\b",
                  lambda m: "hair" if difflib.SequenceMatcher(None, m.group(0).lower(), "hair").ratio() >= 0.75 else m.group(0),
                  text)


def _garment_in(chunk):
    toks = WORD.findall(re.sub(r"-colou?red\b", "", chunk.lower()))
    return any(t in FT.GARMENT for t in toks)


# ----------------------------------------------------------------------------- regex layer
def regex_hair(desc):
    t = _fix_hair_word(desc or "")
    if re.search(r"\bbald\b", t, re.I):
        return "bald"
    for rx in HAIR_PATTERNS:
        for m in rx.finditer(t):
            words = m.group(1).strip().split()
            while words and words[0].lower() in HAIR_WORDS_SKIP:
                words = words[1:]
            h = " ".join(words)
            if h and any(not _empty(x) for x in FT.parse_hair(h)):
                return h
    return None


def regex_clothing(desc):
    desc = desc or ""
    out = []
    for m in CLOTHING_CLAUSE.finditer(desc):
        for chunk in re.split(r",|\band\b|&", m.group(1)):
            chunk = chunk.strip(" .")
            if chunk and _garment_in(chunk):
                out.append(chunk)
    if not out:                                     # no "wearing ..." clause: keep any comma-separated piece with a garment
        for chunk in re.split(r"[,.;]|\band\b|&", desc):
            chunk = chunk.strip(" .")
            if chunk and _garment_in(chunk) and not re.search(r"\bhair\b", chunk, re.I):
                out.append(chunk)
    return list(dict.fromkeys(out))


def regex_marks(desc):
    out = []
    for seg in re.split(r"[.;\n]", desc or ""):
        for piece in re.split(r",(?!\s*(?:left|right)\b)|\band\b", seg):     # keep "gait, left side" together
            piece = MARK_LABEL.sub("", piece.strip()).strip()
            if not piece or NOT_A_MARK.search(piece) or _garment_in(piece):
                continue
            if FT.parse_marks(piece):
                out.append(piece)
    return list(dict.fromkeys(out))


def regex_extract(desc):
    return {"hair": regex_hair(desc), "clothing": regex_clothing(desc), "marks": regex_marks(desc)}


# ----------------------------------------------------------------------------- Granite layer (optional)
PROMPT = """Extract the person's hair, clothing and distinguishing marks from the report.
Return only JSON: {"hair": string or null, "clothing": [list of items], "marks": [list of marks]}.
Copy the words from the report. Use null or [] if the report does not mention it.

Report: Elderly woman, approx. 70-75, found at Old Grain Market, wearing navy coat, grey slacks. Hair: short silver. Mole on left cheek.
JSON: {"hair": "short silver", "clothing": ["navy coat", "grey slacks"], "marks": ["mole on left cheek"]}

Report: My brother, 31, was last seen near Ferry Bridge. Please help.
JSON: {"hair": null, "clothing": [], "marks": []}

Report: {report}
JSON:"""


def parse_model_json(s):
    m = re.search(r"\{.*?\}", s or "", re.S)
    try:
        d = json.loads(m.group(0)) if m else None
    except Exception:
        d = None
    if not isinstance(d, dict):
        return {"hair": None, "clothing": [], "marks": []}
    lst = lambda v: [str(x) for x in v] if isinstance(v, list) else ([str(v)] if v else [])
    return {"hair": d.get("hair") if isinstance(d.get("hair"), str) else None,
            "clothing": lst(d.get("clothing")), "marks": lst(d.get("marks"))}


def in_text(item, text):
    """True if (almost) every word of the item is in the report, allowing small typos. The grounding check."""
    words = re.findall(r"[a-z]+", (text or "").lower())
    iw = re.findall(r"[a-z]+", (item or "").lower())
    if not iw or not words:
        return False
    hit = sum(1 for w in iw if w in words or difflib.get_close_matches(w, words, 1, 0.8))
    return hit / len(iw) >= 0.75


def ground(g, text):
    return {"hair": g["hair"] if in_text(g["hair"], text) else None,
            "clothing": [c for c in g["clothing"] if in_text(c, text)],
            "marks": [m for m in g["marks"] if in_text(m, text)]}


def _dedupe(items):
    items = list(dict.fromkeys(i.strip() for i in items if i and i.strip()))
    return [i for i in items if not any(i.lower() != j.lower() and i.lower() in j.lower() for j in items)]


def combine(r, g, text):
    """Regex answer first, then Granite's grounded answer fills the gaps. No duplicates, no marks inside clothing."""
    g = ground(g, text)
    marks = _dedupe(r["marks"] + g["marks"])
    ml = {m.lower() for m in marks}
    clothing = [c for c in _dedupe(r["clothing"] + g["clothing"]) if c.lower() not in ml]
    ok = lambda h: bool(h) and not any(h.lower() in c.lower() or c.lower() in h.lower() for c in clothing + marks)
    hair = next((h for h in [r["hair"], g["hair"]] if ok(h)), None)
    return {"hair": hair, "clothing": clothing, "marks": marks}


class Granite:
    """Loads in a background thread. state: off | loading | ready | error. Never raises into the request path."""

    def __init__(self, model=None, log=print):
        self.model_name = model or os.environ.get("GRANITE_MODEL", "ibm-granite/granite-4.0-350m")
        self.log = log
        self.state, self.error, self.device = "off", None, None
        self.last_seconds = None
        self._lock = threading.Lock()
        self._tok = self._model = None

    def start(self):
        if self.state != "off":
            return
        self.state = "loading"
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
            dev = os.environ.get("DEVICE", "")
            if not dev:
                try:
                    torch.zeros(1).to("nnpa")
                    dev = "nnpa"
                except Exception:
                    dev = "cpu"
            tok = AutoTokenizer.from_pretrained(self.model_name)
            tok.padding_side = "left"
            if tok.pad_token is None:
                tok.pad_token = tok.eos_token
            try:
                model = AutoModelForCausalLM.from_pretrained(self.model_name, dtype=torch.float32)
            except TypeError:                                  # older transformers call it torch_dtype
                model = AutoModelForCausalLM.from_pretrained(self.model_name, torch_dtype=torch.float32)
            self._tok, self._model, self.device = tok, model.to(dev).eval(), dev
            self.state = "ready"
            self.log(f"[extract] Granite ready on {dev}")
        except Exception as e:
            self.state, self.error = "error", f"{type(e).__name__}: {str(e)[:200]}"
            self.log(f"[extract] Granite unavailable, using regex only. Reason: {self.error}")

    def generate(self, text):
        import torch
        with self._lock:
            t0 = time.time()
            msg = self._tok.apply_chat_template([{"role": "user", "content": PROMPT.replace("{report}", text)}],
                                                add_generation_prompt=True, tokenize=False)
            x = self._tok([msg], return_tensors="pt", padding=True, add_special_tokens=False).to(self.device)
            with torch.no_grad():
                out = self._model.generate(**x, max_new_tokens=120, do_sample=False, pad_token_id=self._tok.pad_token_id)
            s = self._tok.decode(out[0][x["input_ids"].shape[1]:], skip_special_tokens=True)
            self.last_seconds = round(time.time() - t0, 2)
            return parse_model_json(s)


class Extractor:
    def __init__(self, use_granite=None, log=print):
        if use_granite is None:
            use_granite = os.environ.get("REUNITE_GRANITE", "0").strip().lower() in ("1", "true", "yes")
        self.granite = Granite(log=log)
        if use_granite:
            self.granite.start()

    def extract(self, desc):
        r = regex_extract(desc)
        if self.granite.state == "ready" and (desc or "").strip():
            try:
                return combine(r, self.granite.generate(desc), desc)
            except Exception as e:                       # a model hiccup must never block a report
                self.granite.error = f"{type(e).__name__}: {str(e)[:120]}"
        return r

    def fill(self, rec):
        """Fill empty hair / clothing / marks in a cleaned record from its description. Returns the field names filled."""
        desc = rec.get("description") or ""
        need = [k for k in ("hair", "clothing", "marks") if not (rec.get(k) or "").strip()]
        if not need or not desc.strip():
            return []
        ex = self.extract(desc)
        filled = []
        if "hair" in need and ex["hair"]:
            rec["hair"] = ex["hair"]; filled.append("hair")
        if "clothing" in need and ex["clothing"]:
            rec["clothing"] = ", ".join(ex["clothing"]); filled.append("clothing")
        if "marks" in need and ex["marks"]:
            rec["marks"] = "; ".join(ex["marks"]); filled.append("marks")
        return filled

    def info(self):
        g = self.granite
        return {"regex": True, "granite": g.state, "granite_device": g.device, "granite_error": g.error,
                "granite_seconds_last_report": g.last_seconds}
