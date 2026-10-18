"""
extract_check.py - does reading hair / clothing / marks out of the description actually help matching?

  DATA_DIR=../data MODEL_DIR=models python3 extract_check.py            # regex only
  REUNITE_GRANITE=1 python3 extract_check.py                            # regex + Granite (needs torch, transformers)

Test 1  extraction quality. Compare what the extractor read from the description with the structured box that was
        typed for the same report (both turned into categories with the same parsers the matcher uses).
Test 2  matching with text-only reports. On the held-out TEST reports, blank hair / clothing / marks (as if the family
        typed only a paragraph), then rank the true match three ways:
           full boxes (what we have today) / boxes blank / boxes blank + extraction from the paragraph.
        Scenario 1 blanks the missing-person reports only; scenario 2 blanks the found-person records as well.
Writes results/extract_report.json.
"""
import json
import os
import sys

import joblib
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import features as FT          # noqa: E402
from extract import Extractor  # noqa: E402
from scorer import Scorer      # noqa: E402

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(HERE, "..", "data"))
MODEL_DIR = os.environ.get("MODEL_DIR", os.path.join(HERE, "models"))
BOXES = ["hair", "clothing", "marks"]
FT_GARMENT_RE = __import__("re").compile(r"\b(?:" + "|".join(sorted(map(__import__("re").escape, FT.GARMENT), key=len, reverse=True)) + r")\b", __import__("re").I)


def f1(a, b):
    a, b = set(a), set(b)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    tp = len(a & b)
    return 0.0 if tp == 0 else 2 * (tp / len(a)) * (tp / len(b)) / ((tp / len(a)) + (tp / len(b)))


def quality(df, ex):
    """Per box: how often the extracted text means the same as the typed box (only reports where the box was typed)."""
    out = {}
    typed = {k: df[k].fillna("").astype(str).str.strip() != "" for k in BOXES}
    got = [ex.extract(d) for d in df["description"].fillna("")]
    hc, hl, cl, mk, cl_m = [], [], [], [], []
    for i, g in enumerate(got):
        mentions = bool(FT_GARMENT_RE.search(df["description"].fillna("").iloc[i]))
        if typed["hair"].iloc[i]:
            tc, tl = FT.parse_hair(df["hair"].iloc[i]); pc, pl = FT.parse_hair(g["hair"] or "")
            hc.append(float(tc == pc or (pd.isna(tc) and pd.isna(pc)))); hl.append(float(tl == pl or (pd.isna(tl) and pd.isna(pl))))
        if typed["clothing"].iloc[i]:
            sc = f1(FT.parse_clothing(", ".join(g["clothing"])), FT.parse_clothing(df["clothing"].iloc[i]))
            cl.append(sc)
            if mentions:
                cl_m.append(sc)
        if typed["marks"].iloc[i]:
            mk.append(f1({t for t, _, _ in FT.parse_marks("; ".join(g["marks"]))}, {t for t, _, _ in FT.parse_marks(df["marks"].iloc[i])}))
    out["hair_colour_same"], out["hair_length_same"] = round(float(np.mean(hc)), 3), round(float(np.mean(hl)), 3)
    out["clothing_f1"], out["marks_type_f1"] = round(float(np.mean(cl)), 3), round(float(np.mean(mk)), 3)
    out["clothing_f1_when_text_mentions_clothing"] = round(float(np.mean(cl_m)), 3) if cl_m else None
    out["share_of_descriptions_mentioning_clothing"] = round(len(cl_m) / max(len(cl), 1), 3)
    out["reports_scored"] = {"hair": len(hc), "clothing": len(cl), "marks": len(mk)}
    return out


def blank_and_fill(df, rows, ex, fill):
    d = df.copy()
    for i in rows:
        for k in BOXES:
            d.at[d.index[i], k] = ""
        if fill:
            rec = {k: d.at[d.index[i], k] for k in BOXES + ["description"]}
            ex.fill(rec)
            for k in BOXES:
                d.at[d.index[i], k] = rec[k]
    return d


def main():
    rd = lambda n: pd.read_csv(os.path.join(DATA_DIR, n))
    missing, found, truth, places = rd("missing.csv"), rd("found.csv"), rd("truth.csv"), rd("places.csv")
    art = joblib.load(os.path.join(MODEL_DIR, "artifacts.joblib"))
    scorer = Scorer(os.path.join(MODEL_DIR, "scorer.npz"), backend="numpy", log=lambda *a: None)
    ex = Extractor(log=lambda *a: None)
    if ex.granite.state == "loading":
        import time
        while ex.granite.state == "loading":
            time.sleep(1)
    mode = "regex + Granite" if ex.granite.state == "ready" else "regex only"
    print("extractor:", mode, ex.info())

    true_of = dict(zip(truth.missing_id, truth.found_id))
    fpos = {f: j for j, f in enumerate(found["id"])}
    test = [i for i, (mid, sp) in enumerate(zip(missing["id"], missing["split"])) if sp == "test" and mid in true_of]
    res = {"extractor": mode, "reports_in_test": len(test), "found_pool": len(found)}

    print("\n== Test 1: extraction quality (against the typed boxes) ==")
    res["quality_missing"], res["quality_found"] = quality(missing, ex), quality(found, ex)
    print("  missing-person reports:", json.dumps(res["quality_missing"]))
    print("  found-person records:  ", json.dumps(res["quality_found"]))

    def rank(m_df, f_df):
        M, Fd = FT.build_side(m_df, "missing", art), FT.build_side(f_df, "found", art)
        S = scorer.predict(FT.pair_tensor(M, Fd).reshape(-1, len(FT.FEATURES))).reshape(len(m_df), len(f_df))
        r = np.array([1 + int((S[i] > S[i, fpos[true_of[missing["id"].iloc[i]]]]).sum()) for i in test])
        return {"top1": round(float((r <= 1).mean()), 3), "top5": round(float((r <= 5).mean()), 3),
                "top10": round(float((r <= 10).mean()), 3), "median_rank": float(np.median(r))}

    print("\n== Test 2: matching when the boxes are empty (held-out test reports) ==")
    f_test = [j for j in range(len(found)) if found["id"].iloc[j] in {true_of[missing["id"].iloc[i]] for i in test}]
    res["scenario_missing_reports_text_only"] = {
        "full_boxes": rank(missing, found),
        "boxes_blank": rank(blank_and_fill(missing, test, ex, False), found),
        "boxes_blank_plus_extraction": rank(blank_and_fill(missing, test, ex, True), found)}
    res["scenario_both_sides_text_only"] = {
        "full_boxes": res["scenario_missing_reports_text_only"]["full_boxes"],
        "boxes_blank": rank(blank_and_fill(missing, test, ex, False), blank_and_fill(found, f_test, ex, False)),
        "boxes_blank_plus_extraction": rank(blank_and_fill(missing, test, ex, True), blank_and_fill(found, f_test, ex, True))}
    for name in ("scenario_missing_reports_text_only", "scenario_both_sides_text_only"):
        print(" ", name)
        for k, v in res[name].items():
            print(f"    {k:30s} top1 {v['top1']:.1%}  top5 {v['top5']:.1%}  top10 {v['top10']:.1%}  median rank {v['median_rank']:.0f}")
    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    json.dump(res, open(os.path.join(HERE, "results", "extract_report.json"), "w"), indent=1)
    print("\nwritten results/extract_report.json")


if __name__ == "__main__":
    main()
