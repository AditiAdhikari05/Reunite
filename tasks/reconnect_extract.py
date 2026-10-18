"""ReConnect AI free-text extractor: regex (instant) + Granite 350M on the IBM Z AI chip.
    from reconnect_extract import extract, extract_many
    extract("Girl abt 12, parka (maroon), specs")  -> {"hair": ..., "clothing": [...], "marks": [...]}
Set ADAPTER=/path/to/granite_lora to use the Colab fine-tuned model.
"""
import os, re, json, torch
import vocab_canon as vc

MODEL = os.environ.get("GRANITE_MODEL", "ibm-granite/granite-4.0-350m")
PROMPT = """Extract the person's hair, clothing and distinguishing marks from the report.
Return only JSON: {"hair": string or null, "clothing": [list of items], "marks": [list of marks]}.
Copy the words from the report. Use null or [] if the report does not mention it.

Report: Elderly woman, approx. 70-75, found at Old Grain Market, wearing navy coat, grey slacks. Hair: short silver. Mole on left cheek.
JSON: {"hair": "short silver", "clothing": ["navy coat", "grey slacks"], "marks": ["mole on left cheek"]}

Report: My brother, 31, was last seen near Ferry Bridge. Please help.
JSON: {"hair": null, "clothing": [], "marks": []}

Report: {report}
JSON:"""
_tok = _model = DEVICE = None

def _device():
    if os.environ.get("DEVICE"):
        return os.environ["DEVICE"]
    try:
        torch.zeros(1).to("nnpa"); return "nnpa"
    except Exception:
        return "cpu"

def _load():
    global _tok, _model, DEVICE
    if _model is None:
        from transformers import AutoTokenizer, AutoModelForCausalLM
        DEVICE = _device()
        _tok = AutoTokenizer.from_pretrained(MODEL); _tok.padding_side = "left"
        if _tok.pad_token is None:
            _tok.pad_token = _tok.eos_token
        _model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.float32)
        if os.environ.get("ADAPTER"):
            from peft import PeftModel
            _model = PeftModel.from_pretrained(_model, os.environ["ADAPTER"])
        _model = _model.to(DEVICE).eval()
    return _tok, _model

def _parse(s):
    m = re.search(r"\{.*?\}", s, re.S)
    try:
        d = json.loads(m.group(0)) if m else None
    except Exception:
        d = None
    if not isinstance(d, dict):
        return {"hair": None, "clothing": [], "marks": []}
    lst = lambda v: [str(x) for x in v] if isinstance(v, list) else ([str(v)] if v else [])
    return {"hair": d.get("hair") if isinstance(d.get("hair"), str) else None,
            "clothing": lst(d.get("clothing")), "marks": lst(d.get("marks"))}

def granite(texts, batch=8):
    tok, model = _load(); out = []
    for i in range(0, len(texts), batch):
        msgs = [tok.apply_chat_template([{"role": "user", "content": PROMPT.replace("{report}", t)}],
                                        add_generation_prompt=True, tokenize=False) for t in texts[i:i + batch]]
        x = tok(msgs, return_tensors="pt", padding=True, add_special_tokens=False).to(DEVICE)
        with torch.no_grad():
            g = model.generate(**x, max_new_tokens=120, do_sample=False, pad_token_id=tok.pad_token_id)
        out += [_parse(tok.decode(o[x["input_ids"].shape[1]:], skip_special_tokens=True)) for o in g]
    return out

HAIR_NEAR = [re.compile(r"([\w\- ]{2,20}?)\s+hair\b", re.I),
             re.compile(r"\bhair\s*(?:is|:)?\s*([^,.;]{2,25})", re.I)]

def _hair_from_text(text):
    for rx in HAIR_NEAR:
        m = rx.search(_fix_hair(text or ""))
        if m:
            h = re.sub(r"^(?:has|with|w/|and)\s+", "", m.group(1).strip(), flags=re.I)
            if h:
                return h
    return None

def _dedupe(items):
    items = list(dict.fromkeys(i.strip() for i in items if i and i.strip()))
    return [i for i in items if not any(i.lower() != j.lower() and i.lower() in j.lower() for j in items)]

import difflib

def _in_text(item, text):
    """True if (almost) every word of the item appears in the report, allowing small typos."""
    words = re.findall(r"[a-z]+", text.lower())
    iw = re.findall(r"[a-z]+", (item or "").lower())
    if not iw:
        return False
    hit = sum(1 for w in iw if w in words or difflib.get_close_matches(w, words, 1, 0.8))
    return hit / len(iw) >= 0.75

def _ground(g, text):
    """Drop anything Granite made up (e.g. copied from the prompt example)."""
    return {"hair": g["hair"] if _in_text(g["hair"], text) else None,
            "clothing": [c for c in g["clothing"] if _in_text(c, text)],
            "marks": [m for m in g["marks"] if _in_text(m, text)]}

def _fix_hair(text):
    """Treat misspellings like 'hari' or 'hiar' as 'hair'."""
    return re.sub(r"\bh[a-z]{2,4}\b", lambda m: "hair" if difflib.SequenceMatcher(None, m.group(0).lower(), "hair").ratio() >= 0.75 else m.group(0), text)

def combine(r, g, text):
    """Regex first, then simple hair patterns, then Granite; no duplicates, no marks inside clothing."""
    g = _ground(g, text)
    marks = _dedupe(r["marks"] + g["marks"])
    ml = {m.lower() for m in marks}
    clothing = [c for c in _dedupe(r["clothing"] + g["clothing"]) if c.lower() not in ml]
    ok = lambda h: bool(h) and not any(h.lower() in c.lower() or c.lower() in h.lower() for c in clothing + marks)
    hair = next((h for h in [r["hair"], _hair_from_text(text), g["hair"]] if ok(h)), None)
    return {"hair": hair, "clothing": clothing, "marks": marks}

def extract_many(texts, batch=8):
    regex = [vc.ORIGINAL.regex_extract(t) for t in texts]
    gran = granite(texts, batch)
    return [combine(r, g, t) for r, g, t in zip(regex, gran, texts)]

def extract(text):
    return extract_many([text])[0]
