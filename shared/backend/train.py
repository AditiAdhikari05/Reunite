"""
train.py - trains the match scorer on the synthetic data and measures how good it is.

Run:   python train.py --data ../data --out models
Takes a few minutes. Trains on the CPU (scikit-learn); inference later runs through TensorFlow / the chip.

What it does
  1. builds pair features for every (report, found person) combination
  2. trains on the 'dev' reports only, and measures everything on the 'test' reports it has never seen
  3. compares against two baselines: keyword search (TF-IDF on the description) and hand-weighted rules
  4. runs an ablation (drop one group of features at a time)
  5. picks the review threshold with cross-validation on dev, and writes models/ + demo_cases.json
"""
import argparse
import json
import os
import sys
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.neural_network import MLPClassifier

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import features as FT                      # noqa: E402
from scorer import save_weights            # noqa: E402

N_RAND_NEG, N_HARD_NEG, POS_WEIGHT, PLACE_BLANK = 60, 60, 10.0, 0.15


def load_dataset(data_dir):
    rd = lambda n: pd.read_csv(os.path.join(data_dir, n))
    return rd("missing.csv"), rd("found.csv"), rd("truth.csv"), rd("places.csv")


def true_matrix(M_ids, F_ids, truth):
    mi, fi = {k: i for i, k in enumerate(M_ids)}, {k: i for i, k in enumerate(F_ids)}
    pairs = [(mi[a], fi[b]) for a, b in zip(truth.missing_id, truth.found_id)]
    j = np.full(len(M_ids), -1)
    for a, b in pairs:
        j[a] = b
    return j                                   # j[i] = index of the true found person for report i, or -1


def rank_metrics(S, true_j, rows):
    """S: (n_missing, n_found) scores. Rank of the true match among all found people, for reports that have one."""
    rows = [i for i in rows if true_j[i] >= 0]
    r = np.array([1 + int((S[i] > S[i, true_j[i]]).sum()) for i in rows])
    return {"queries": len(r), "top1": float((r <= 1).mean()), "top5": float((r <= 5).mean()),
            "top10": float((r <= 10).mean()), "mrr": float((1 / r).mean()), "median_rank": float(np.median(r))}, r


def make_training_rows(X, true_j, rows, base_score, rng, blank_place=True):
    """Positives + hard negatives (highest hand-rule score) + random negatives, per report.
    Positives are up-weighted at fit time (POS_WEIGHT) instead of duplicated: duplicated rows leak into the
    network's early-stopping validation set and make it overfit."""
    Xs, ys = [], []
    nf = X.shape[1]
    for i in rows:
        cand = np.ones(nf, bool)
        if true_j[i] >= 0:
            cand[true_j[i]] = False
        idx = np.flatnonzero(cand)
        hard = idx[np.argsort(-base_score[i, idx])[:N_HARD_NEG]]
        rest = np.setdiff1d(idx, hard)
        rnd = rng.choice(rest, size=min(N_RAND_NEG, len(rest)), replace=False)
        neg = np.concatenate([hard, rnd])
        Xs.append(X[i, neg]); ys.append(np.zeros(len(neg)))
        if true_j[i] >= 0:
            Xs.append(X[i, true_j[i]][None]); ys.append(np.ones(1))
    Xa, ya = np.vstack(Xs).copy(), np.concatenate(ys)
    if blank_place:        # teach the model what to do when a place is not recognised
        b = rng.random(len(Xa)) < PLACE_BLANK
        for n in ("place_known", "km_norm", "speed_norm"):
            Xa[b, FT.COL[n]] = 0
    return Xa, ya


def fit_model(kind, Xtr, ytr, seed=0):
    mu, sd = Xtr.mean(0), Xtr.std(0)
    sd[sd < 1e-6] = 1.0
    Z = (Xtr - mu) / sd
    w = np.where(ytr == 1, POS_WEIGHT, 1.0)
    if kind == "logreg":
        clf = LogisticRegression(C=1.0, max_iter=2000).fit(Z, ytr, sample_weight=w)
        layers = [(clf.coef_.T, clf.intercept_)]
    else:
        sizes = {"mlp_small": (64, 32), "mlp_wide": (256, 256, 64)}[kind]
        clf = MLPClassifier(hidden_layer_sizes=sizes, alpha=1e-2, batch_size=512, max_iter=60, early_stopping=True,
                            n_iter_no_change=6, random_state=seed).fit(Z, ytr, sample_weight=w)
        layers = list(zip(clf.coefs_, clf.intercepts_))
    # fold the standardisation into the first layer so the saved network takes raw features
    W0, b0 = layers[0]
    layers[0] = (W0 / sd[:, None], b0 - (mu / sd) @ W0)
    return [(np.asarray(W, np.float32), np.asarray(b, np.float32)) for W, b in layers]


def forward(layers, X):
    h = X.reshape(-1, X.shape[-1]).astype(np.float32)
    for W, b in layers[:-1]:
        h = np.maximum(h @ W + b, 0)
    W, b = layers[-1]
    z = np.clip(h @ W + b, -30, 30)
    return (1 / (1 + np.exp(-z)))[:, 0].reshape(X.shape[:-1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="../data")
    ap.add_argument("--out", default="models")
    ap.add_argument("--quick", action="store_true", help="skip ablation (faster)")
    a = ap.parse_args()
    t_start = time.time()
    os.makedirs(a.out, exist_ok=True)
    missing, found, truth, places = load_dataset(a.data)
    art = FT.Artifacts(places).fit(missing, found)
    M, Fd = FT.build_side(missing, "missing", art), FT.build_side(found, "found", art)
    X = FT.pair_tensor(M, Fd)
    true_j = true_matrix(M.ids, Fd.ids, truth)
    dev = np.flatnonzero(missing["split"].to_numpy() == "dev")
    test = np.flatnonzero(missing["split"].to_numpy() == "test")
    rules = FT.rules_score(X)
    print(f"features {X.shape}, dev reports {len(dev)}, test reports {len(test)}  ({time.time()-t_start:.1f}s)")

    # ---- 1. compare model types by cross-validation on dev only
    rng = np.random.default_rng(0)
    folds = list(GroupKFold(n_splits=4).split(dev, groups=dev))
    cv, oof = {}, {}
    for kind in ["logreg", "mlp_small", "mlp_wide"]:
        S = np.zeros((len(missing), len(found)), np.float32)
        t0 = time.time()
        for tr, va in folds:
            Xtr, ytr = make_training_rows(X, true_j, dev[tr], rules, rng)
            layers = fit_model(kind, Xtr, ytr)
            S[dev[va]] = forward(layers, X[dev[va]])
        m, _ = rank_metrics(S, true_j, dev)
        cv[kind], oof[kind] = m, S
        print(f"  cv {kind:10s} top1 {m['top1']:.3f} top5 {m['top5']:.3f} mrr {m['mrr']:.3f}  ({time.time()-t0:.0f}s)")
    choice = max(cv, key=lambda k: cv[k]["mrr"])          # chosen purely by validation score
    print("chosen model:", choice, "(best cross-validated MRR on dev; no other criterion)")

    # ---- 2. review threshold from out-of-fold dev scores
    S_oof = oof[choice]
    top1 = S_oof[dev].max(1)
    hit = np.array([S_oof[i].argmax() == true_j[i] for i in dev])
    thr = 0.5
    for t in np.linspace(0.05, 0.99, 95):
        sel = top1 >= t
        if sel.sum() >= 10 and hit[sel].mean() >= 0.85:
            thr = float(t); break

    # ---- 3. final model on all dev, evaluate on test
    def train_eval(cols, kind=choice):
        keep = np.array([c in cols for c in FT.FEATURES])
        Xtr, ytr = make_training_rows(X * keep, true_j, dev, FT.rules_score(X), np.random.default_rng(1))
        layers = fit_model(kind, Xtr, ytr, seed=1)
        S = forward(layers, X * keep)
        return layers, S
    layers, S_final = train_eval(FT.FEATURES)
    alt = {}
    for kind in ("logreg", "mlp_small", "mlp_wide"):
        alt[kind] = (layers, S_final) if kind == choice else train_eval(FT.FEATURES, kind)
    res = {"keyword baseline (TF-IDF on description)": rank_metrics(X[:, :, FT.COL["desc_word_sim"]], true_j, test)[0],
           "hand-weighted rules": rank_metrics(rules, true_j, test)[0],
           f"learned scorer ({choice}) - DEPLOYED": rank_metrics(S_final, true_j, test)[0]}
    for kind in ("logreg", "mlp_small", "mlp_wide"):
        if kind != choice:
            res[f"learned scorer ({kind}) - not deployed"] = rank_metrics(alt[kind][1], true_j, test)[0]
    for k, v in res.items():
        print(f"  test  {k:52s} top1 {v['top1']:.3f} top5 {v['top5']:.3f} top10 {v['top10']:.3f} mrr {v['mrr']:.3f}")

    sel = S_final[test].max(1) >= thr
    has = true_j[test] >= 0
    top1_ok = np.array([S_final[i].argmax() == true_j[i] for i in test])
    review = {"threshold": thr, "flagged_share_of_reports_with_match": float(sel[has].mean()),
              "top1_precision_when_flagged": float(top1_ok[sel & has].sum() / max(1, sel.sum())),
              "reports_without_match_flagged": float(sel[~has].mean()) if (~has).any() else None}
    print("  review threshold", review)

    ablation = {}
    if not a.quick:
        for g, cols in FT.FEATURE_GROUPS.items():
            _, S = train_eval([c for c in FT.FEATURES if c not in cols])
            ablation[f"without {g}"] = rank_metrics(S, true_j, test)[0]
            print(f"  ablation without {g:42s} top1 {ablation[f'without {g}']['top1']:.3f} top5 {ablation[f'without {g}']['top5']:.3f}")

    # ---- 4. demo cases: 5 random test pairs, kept out of the pre-loaded data so they can be submitted live
    rd = np.random.default_rng(7)
    cand = [i for i in test if true_j[i] >= 0]
    demo_idx = [int(i) for i in rd.choice(cand, size=5, replace=False)]
    cases = []
    for i in demo_idx:
        m, f = missing.iloc[i], found.iloc[true_j[i]]
        rank = 1 + int((S_final[i] > S_final[i, true_j[i]]).sum())
        clean = lambda r, drop: {k: (None if pd.isna(v) else (v.item() if hasattr(v, "item") else v)) for k, v in r.items() if k not in drop}
        cases.append({"missing_id": m["id"], "found_id": f["id"], "true_rank_in_full_pool": rank,
                      "missing": clean(m, ["id", "split"]), "found": clean(f, ["id"])})
    print("  demo cases (rank of true match among all 600 found):", [c["true_rank_in_full_pool"] for c in cases])

    joblib.dump(art, os.path.join(a.out, "artifacts.joblib"))
    save_weights(os.path.join(a.out, "scorer.npz"), layers)
    for kind, (lay, _) in alt.items():          # other variants, only used for side-by-side benchmarks
        save_weights(os.path.join(a.out, f"scorer_{kind}.npz"), lay)
    json.dump(cases, open(os.path.join(a.out, "demo_cases.json"), "w"), indent=1)
    meta = {"trained_at": time.strftime("%Y-%m-%d %H:%M:%S"), "model": choice, "layers": [list(W.shape) for W, _ in layers],
            "n_features": len(FT.FEATURES), "features": FT.FEATURES, "review_threshold": thr,
            "cross_validation_dev": cv, "test_results": res, "review_policy_test": review, "ablation_test": ablation,
            "dev_reports": int(len(dev)), "test_reports": int(len(test)), "found_pool": int(len(found)),
            "notes": ["All data is synthetic. Numbers are on held-out 'test' reports the model never trained on.",
                      "In the generator, found_time is always 1-72 h after last_seen_time; real data would not be that tidy. "
                      "The model only sees 'found before last seen' and the speed needed, not the raw time gap.",
                      "Scores are ranking scores, not probabilities of being the same person."]}
    json.dump(meta, open(os.path.join(a.out, "meta.json"), "w"), indent=1)
    print(f"saved to {a.out}/  total {time.time()-t_start:.0f}s")


if __name__ == "__main__":
    main()
