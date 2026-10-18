"""Map free wording back to canonical categories, using a vocabulary (make_data.py's by default).
Used for (a) the regex extractor and (b) scoring any extractor against the structured columns.

  import vocab_canon as vc
  vc.ORIGINAL                -> Canon built from make_data.py (what a hand-written normaliser knows)
  vc.Canon.from_module(md)   -> Canon for any vocabulary, e.g. after make_data_hard patched it
"""
import copy, re
import make_data as md

def _syn_map(d):
    out = {}
    for key, words in d.items():
        for w in [key] + list(words):
            out.setdefault(w.lower(), set()).add(key)
    return out

def _alternation(words):
    words = sorted(words, key=len, reverse=True)          # longest first: "dark brown" before "dark"
    return re.compile(r"(?<![\w-])(" + "|".join(re.escape(w) for w in words) + r")(?![\w-])", re.I)

def f1(pred, gold):
    if not pred and not gold:
        return 1.0
    if not pred or not gold:
        return 0.0
    tp = len(pred & gold)
    if tp == 0:
        return 0.0
    p, r = tp / len(pred), tp / len(gold)
    return 2 * p * r / (p + r)

HAIR_CONTEXT = [re.compile(r"\b(?:has|with|w/)\s+([^.;]{2,40}?)\s+hair\b", re.I), re.compile(r"\bhair:\s*([^.;]{2,40})", re.I)]


class Canon:
    def __init__(self, hair_color, hair_len, colors, garments, marks):
        self.HAIR_COLOR_SYN, self.HAIR_LEN_SYN = _syn_map(hair_color), _syn_map(hair_len)
        self.COLOR_SYN, self.GARMENT_SYN = _syn_map(colors), _syn_map(garments)
        self.RE_GARMENT, self.RE_COLOR = _alternation(self.GARMENT_SYN), _alternation(self.COLOR_SYN)
        self.RE_HAIR_COLOR, self.RE_HAIR_LEN = _alternation(self.HAIR_COLOR_SYN), _alternation(self.HAIR_LEN_SYN)
        self.MARK_PATTERNS = []
        for key, (canon, alts) in marks.items():
            for t in [canon] + alts:
                pat = re.escape(t.lower()).replace(r"\{side\}", r"(left|right)")
                self.MARK_PATTERNS.append((key, re.compile(r"\b" + pat + r"\b", re.I), "{side}" in t))
        self.MARK_PATTERNS.sort(key=lambda x: -len(x[1].pattern))

    @classmethod
    def from_module(cls, m):
        return cls(copy.deepcopy(m.HAIR_COLOR), copy.deepcopy(m.HAIR_LENGTH), copy.deepcopy(m.COLORS), copy.deepcopy(m.GARMENTS), copy.deepcopy(m.MARKS))

    # ------------------------------------------------ canonicalisers
    def hair(self, text):
        """-> (possible colour keys, possible length keys, bald?)"""
        t = (text or "").lower()
        cols = set().union(set(), *[self.HAIR_COLOR_SYN[m.group(1).lower()] for m in self.RE_HAIR_COLOR.finditer(t)])
        lens = set().union(set(), *[self.HAIR_LEN_SYN[m.group(1).lower()] for m in self.RE_HAIR_LEN.finditer(t)])
        return cols, lens, "bald" in t

    def clothing(self, text_or_list):
        """-> set of (colour key or None, garment key)"""
        parts = text_or_list if isinstance(text_or_list, list) else re.split(r"[,;]| and ", text_or_list or "")
        out = set()
        for p in parts:
            g = self.RE_GARMENT.search(str(p))
            if not g:
                continue
            c = self.RE_COLOR.search(str(p))
            out.add((sorted(self.COLOR_SYN[c.group(1).lower()])[0] if c else None, sorted(self.GARMENT_SYN[g.group(1).lower()])[0]))
        return out

    def marks(self, text_or_list, spans=False):
        """-> set of (mark key, side or None); spans=True returns the matched phrases"""
        t = " ; ".join(text_or_list) if isinstance(text_or_list, list) else (text_or_list or "")
        out, used, texts = set(), [], []
        for key, rx, sided in self.MARK_PATTERNS:
            for m in rx.finditer(t):
                if any(m.start() < e and s < m.end() for s, e in used):
                    continue
                used.append((m.start(), m.end())); texts.append(m.group(0))
                out.add((key, m.group(1).lower() if sided else None))
        return texts if spans else out

    # ------------------------------------------------ regex extractor (the fallback)
    def regex_extract(self, desc):
        d = desc or ""
        hair_txt = "bald" if re.search(r"\bbald\b", d, re.I) else None
        if not hair_txt:
            for rx in HAIR_CONTEXT:
                m = rx.search(d)
                if m:
                    hair_txt = m.group(1).strip(); break
        cloth = []
        m = re.search(r"(?:wearing:?|clothing:|clothes:|last seen in)\s+([^.]+)", d, re.I)
        if m:
            cloth = [c.strip() for c in re.split(r",| and ", m.group(1)) if self.RE_GARMENT.search(c)]
        return {"hair": hair_txt, "clothing": cloth, "marks": self.marks(d, spans=True)}

    # ------------------------------------------------ score a prediction against the structured columns
    def score(self, pred, row):
        gc, gl, gb = self.hair(row.get("hair", ""))
        pc, pl, pb = self.hair(pred.get("hair") or "")
        pm, gm = self.marks(pred.get("marks") or []), self.marks(row.get("marks", ""))
        pcl, gcl = self.clothing(pred.get("clothing") or []), self.clothing(row.get("clothing", ""))
        return {
            "hair_color": float((not gc and not pc and gb == pb) or bool(gc & pc) or (gb and pb)),
            "hair_length": float((not gl and not pl and gb == pb) or bool(gl & pl) or (gb and pb)),
            "clothing_f1": f1(pcl, gcl),
            "garment_f1": f1({g for _, g in pcl}, {g for _, g in gcl}),
            "marks_f1": f1({k for k, _ in pm}, {k for k, _ in gm}),
            "marks_side_f1": f1(pm, gm),
        }


ORIGINAL = Canon.from_module(md)
