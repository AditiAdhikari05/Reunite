"""
e2e_check.py - end-to-end proof that the matcher works, for the demo and the presentation.   Run:  python3 e2e_check.py

Part A  Accuracy. Loads the real engine and the synthetic data, then scores the HELD-OUT test reports (reports the model
        never trained on) against every found person, and checks where the true match lands.
Part B  Live flow. Starts a PRIVATE copy of the web app (own temporary data, so your real app and demo cases stay untouched)
        and walks through it over HTTP exactly as the front end does: family signs up, files a report, an authority adds a
        found person, the system flags it, the authority confirms, the family sees "reunited".

Writes results/e2e_report.md and results/e2e_results.json (numbers and example cases to copy into the slides).
Exit code 0 = everything passed. Needs: models/ from train.py, the CSV files in ../data.
"""
import http.cookiejar
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(HERE, "..", "data"))
MODEL_DIR = os.environ.get("MODEL_DIR", os.path.join(HERE, "models"))
OUT_DIR = os.path.join(HERE, "results")
passed = failed = 0


def check(name, cond, extra=""):
    global passed, failed
    passed += bool(cond)
    failed += (not cond)
    print(("  PASS " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    return bool(cond)


# ======================================================================================= Part A
def part_a():
    print("\n=== Part A: accuracy on held-out reports, through the real engine ===")
    from engine import Engine
    tmp = tempfile.mkdtemp()
    eng = Engine(DATA_DIR, MODEL_DIR, os.path.join(tmp, "state.json"), backend="numpy", log=lambda *a: None)
    missing = pd.read_csv(os.path.join(DATA_DIR, "missing.csv"))
    truth = pd.read_csv(os.path.join(DATA_DIR, "truth.csv"))
    true_of = dict(zip(truth.missing_id, truth.found_id))
    test_ids = set(missing.loc[missing["split"] == "test", "id"])
    mids, fids = eng.mdf["id"].tolist(), eng.fdf["id"].tolist()
    fpos = {f: j for j, f in enumerate(fids)}
    ranks, top_flag, flagged_correct, flagged_n = [], [], 0, 0
    nomatch_total = nomatch_flagged = 0
    for i, mid in enumerate(mids):
        if mid not in test_ids:
            continue
        row = eng.S[i]
        top_j = int(np.argmax(row))
        flagged = row[top_j] >= eng.threshold
        tf = true_of.get(mid)
        if tf is None:
            nomatch_total += 1
            nomatch_flagged += int(flagged)
            continue
        if tf not in fpos:                                   # its true match is one of the 5 held back for the live demo
            continue
        ranks.append(1 + int((row > row[fpos[tf]]).sum()))
        if flagged:
            flagged_n += 1
            flagged_correct += int(top_j == fpos[tf])
    r = np.array(ranks)
    res = {"reports_with_a_true_match": int(len(r)), "found_people_searched": len(fids),
           "top1": float((r <= 1).mean()), "top3": float((r <= 3).mean()), "top5": float((r <= 5).mean()),
           "top10": float((r <= 10).mean()), "median_rank": float(np.median(r)),
           "chance_top1": 1 / len(fids), "review_threshold": eng.threshold,
           "flagged_share": flagged_n / len(r), "flagged_top1_precision": (flagged_correct / flagged_n) if flagged_n else None,
           "reports_without_match": nomatch_total, "false_alarm_share": (nomatch_flagged / nomatch_total) if nomatch_total else None}
    print(f"  {res['reports_with_a_true_match']} held-out reports with a real match, searched against {res['found_people_searched']} found people")
    print(f"  true match ranked 1st: {res['top1']:.1%}   top 3: {res['top3']:.1%}   top 5: {res['top5']:.1%}   top 10: {res['top10']:.1%}"
          f"   (guessing would give {res['chance_top1']:.2%} for 1st)")
    print(f"  review threshold {eng.threshold:.2f}: flags {res['flagged_share']:.0%} of reports; when it flags, the top pick is right "
          f"{res['flagged_top1_precision']:.0%} of the time; false alarms on reports with no match: "
          f"{res['false_alarm_share']:.0%} ({nomatch_flagged} of {nomatch_total})")
    check("true match is in the top 5 for at least 85% of held-out reports", res["top5"] >= 0.85, res["top5"])
    check("ranked 1st far better than chance", res["top1"] > 50 * res["chance_top1"], res["top1"])
    check("flagged picks are right at least 85% of the time", (res["flagged_top1_precision"] or 0) >= 0.85, res["flagged_top1_precision"])
    meta = json.load(open(os.path.join(MODEL_DIR, "meta.json")))
    tr = meta["test_results"]
    keyword = next(v for k, v in tr.items() if k.startswith("keyword"))
    rules = next(v for k, v in tr.items() if k.startswith("hand-weighted"))
    res["baselines_from_training"] = {"keyword_search": {"top1": keyword["top1"], "top5": keyword["top5"]},
                                      "hand_weighted_rules": {"top1": rules["top1"], "top5": rules["top5"]}}
    res["ablation_from_training"] = {k: {"top1": v["top1"], "top5": v["top5"]} for k, v in meta["ablation_test"].items()}
    return res


# ======================================================================================= Part B
class Client:
    def __init__(self, base):
        self.base = base
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers={"Content-Type": "application/json"})
        try:
            with self.op.open(req, timeout=60) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw or b"null")
            except ValueError:
                return e.code, raw.decode(errors="replace")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def part_b():
    print("\n=== Part B: live flow over HTTP against a private copy of the app ===")
    tmp = tempfile.mkdtemp()
    port = free_port()
    env = dict(os.environ, PORT=str(port), STATE_PATH=os.path.join(tmp, "state", "state.json"),
               ADMIN_EMAIL="e2e-admin@example.org", ADMIN_PASSWORD="e2e-admin-password", FRONTEND_DIR=tmp,
               DATA_DIR=DATA_DIR, MODEL_DIR=MODEL_DIR)
    env.pop("STATE_KEY", None)
    log = open(os.path.join(tmp, "app.log"), "w")
    proc = subprocess.Popen([sys.executable, os.path.join(HERE, "app.py")], env=env, stdout=log, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    anon, fam, auth = Client(base), Client(base), Client(base)
    out = {"cases": []}
    try:
        for _ in range(120):
            try:
                if anon.call("GET", "/api/health")[0] == 200:
                    break
            except Exception:
                pass
            time.sleep(0.5)
        else:
            raise RuntimeError("the private app did not start; see " + os.path.join(tmp, "app.log"))
        s, h = anon.call("GET", "/api/health")
        check("server is up and has data", s == 200 and h["reports"] > 300 and h["found_people"] > 500, h)
        out["scorer"] = h["scorer"]
        check("family cannot read authority data", fam.call("GET", "/api/missing")[0] == 401)
        s, u = auth.call("POST", "/api/auth/login", {"email": env["ADMIN_EMAIL"], "password": env["ADMIN_PASSWORD"], "role": "authority"})
        check("authority can sign in with email and password", s == 200 and u["user"]["role"] == "admin", u)
        s, u = fam.call("POST", "/api/auth/signup", {"name": "E2E Family", "email": "e2e-family@example.org", "phone": "555-0000", "password": "e2e-family-pass"})
        check("family can sign up", s == 201, u)
        s, m = fam.call("POST", "/api/family/members", {"name": "Demo Person", "relationship": "relative"})
        pid = m["id"]
        s, cases = anon.call("GET", "/api/demo-cases")
        good = [c for c in cases if c["good_for_live_demo"]]
        check("there are demo cases that start as 'searching' and end as 'possible match'", len(good) >= 2, f"{len(good)} good of {len(cases)}")
        for c in good[:3]:
            print(f"\n  -- {c['title']}")
            s, r = fam.call("POST", "/api/missing", dict(c["missing"], member_id=pid))
            mid = r["id"]
            check(f"{mid}: report filed, status is 'searching'", s == 201 and r["status"] == "searching", r)
            t0 = time.time()
            s, fr = auth.call("POST", "/api/found", c["found"])
            dt = time.time() - t0
            fid = fr["id"]
            check(f"{fid}: found person added and scored against all reports in {dt:.2f}s", s == 201 and dt < 5, (s, dt))
            s, m = auth.call("GET", f"/api/matches/{mid}")
            ids = [x["found_id"] for x in m["candidates"]]
            rank = ids.index(fid) + 1 if fid in ids else None
            check(f"{mid}: true match is ranked #{rank} of {len(ids)} shown", rank == 1, ids[:3])
            s, st = anon.call("GET", f"/api/status/{mid}")
            check(f"{mid}: family status flips to 'possible_match'", st["status"] == "possible_match", st)
            check(f"{mid}: family sees nothing but status and contact line", set(st) == {"id", "status", "message", "authority_contact"}, st)
            s, d = auth.call("POST", f"/api/matches/{mid}/decision", {"found_id": fid, "decision": "confirm"})
            check(f"{mid}: authority confirms -> 'reunited'", s == 200 and anon.call("GET", f"/api/status/{mid}")[1]["status"] == "reunited", d)
            s, rep = fam.call("GET", "/api/family/reports")
            check(f"{mid}: family's own list shows 'reunited'", any(x["id"] == mid and x["status"] == "reunited" for x in rep), rep)
            auth.call("POST", f"/api/matches/{mid}/decision", {"found_id": fid, "decision": "undo"})
            top = m["candidates"][0]
            out["cases"].append({"title": c["title"], "missing_id": mid, "found_id": fid, "rank_of_true_match": rank, "score": top["score"],
                                 "missing": {k: c["missing"].get(k) for k in ("age_min", "age_max", "gender", "hair", "clothing", "marks", "last_seen_place", "last_seen_time")},
                                 "found": {k: c["found"].get(k) for k in ("age_min", "age_max", "gender", "hair", "clothing", "marks", "found_place", "found_time")},
                                 "reasons": top["reasons"], "runner_up_scores": [x["score"] for x in m["candidates"][1:4]]})
        s, pf = anon.call("POST", "/api/public/found", dict(good[0]["found"], reporter_name="Passer-by", reporter_phone="555-1111"))
        check("a member of the public can report a found person", s == 201 and set(pf) == {"id"}, pf)
        s, b = anon.call("GET", "/api/benchmark")
        check("benchmark page data is available", s == 200 and "accuracy" in b and "speed" in b)
        out["benchmark_live"] = {k: b.get(k) for k in ("accuracy", "speed", "chip", "live_rescan")}
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except Exception:
            proc.kill()
    return out


def write_reports(a, b):
    os.makedirs(OUT_DIR, exist_ok=True)
    json.dump({"accuracy_heldout": a, "live_flow": b, "checks_passed": passed, "checks_failed": failed},
              open(os.path.join(OUT_DIR, "e2e_results.json"), "w"), indent=1, default=str)
    base, ab = a["baselines_from_training"], a["ablation_from_training"]
    L = ["# End-to-end results (synthetic data)", "",
         f"Held-out reports (never used for training): **{a['reports_with_a_true_match']}**, each searched against **{a['found_people_searched']}** found people.", "",
         "| Method | Right person ranked 1st | In top 5 |", "|---|---|---|",
         f"| Keyword search on the description | {base['keyword_search']['top1']:.0%} | {base['keyword_search']['top5']:.0%} |",
         f"| Hand-weighted rules | {base['hand_weighted_rules']['top1']:.0%} | {base['hand_weighted_rules']['top5']:.0%} |",
         f"| **Our learned scorer (deployed)** | **{a['top1']:.0%}** | **{a['top5']:.0%}** |", "",
         f"Top 3: {a['top3']:.0%}. Top 10: {a['top10']:.0%}. Guessing would put the right person first {a['chance_top1']:.2%} of the time.", "",
         f"Human-review flag (score >= {a['review_threshold']:.2f}): flags {a['flagged_share']:.0%} of reports; the flagged top pick is right "
         f"{a['flagged_top1_precision']:.0%} of the time; false alarms on reports with no real match: {a['false_alarm_share']:.0%}. "
         "A person still confirms every match.", "", "## What each kind of information is worth (removed one at a time)", "",
         "| Removed | Right person ranked 1st | In top 5 |", "|---|---|---|"]
    L += [f"| {k.replace('ablation without ', '')} | {v['top1']:.0%} | {v['top5']:.0%} |" for k, v in ab.items()]
    L += ["", "## Live walk-through (HTTP, as the front end does it)", ""]
    for c in b["cases"]:
        L += [f"**{c['title']}**: true match ranked #{c['rank_of_true_match']}, score {c['score']}, runner-ups {c['runner_up_scores']}", ""]
        L += [f"- {'matched' if r['matched'] else 'differs'}: {r['label']}" for r in c["reasons"]]
        L += [""]
    L += [f"Checks passed: {passed}, failed: {failed}.", "", "Caveats: synthetic data; scores are ranking scores, not probabilities; "
          "the found-time window in the generator is simpler than real life."]
    open(os.path.join(OUT_DIR, "e2e_report.md"), "w").write("\n".join(L))


if __name__ == "__main__":
    a = part_a()
    b = part_b()
    write_reports(a, b)
    print(f"\n{passed} passed, {failed} failed. Report: {os.path.join(OUT_DIR, 'e2e_report.md')}")
    sys.exit(1 if failed else 0)
