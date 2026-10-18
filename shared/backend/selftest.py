"""
selftest.py - checks the whole API end to end, including accounts, using temporary files.
Run:  python3 selftest.py        (needs models/ from train.py). Does not touch your real saved data.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.pop("STATE_KEY", None)
import app as appmod  # noqa: E402
from accounts import Accounts  # noqa: E402
from engine import Engine  # noqa: E402

H = {"X-Auth-Pin": "ignored"}      # old front ends may still send this header; it must have no effect
passed = failed = 0


def check(name, cond, extra=""):
    global passed, failed
    passed += bool(cond)
    failed += (not cond)
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))


def main():
    tmp = tempfile.mkdtemp()
    state, users = os.path.join(tmp, "state.json"), os.path.join(tmp, "users.json")
    front = os.path.join(tmp, "front")
    os.makedirs(os.path.join(front, "family"))
    for p, txt in (("index.html", "home"), ("family/index.html", "fam"), ("family/family.js", "js")):
        open(os.path.join(front, p), "w").write(txt)
    os.environ["FRONTEND_DIR"] = front

    mk = lambda: Engine(appmod.DATA_DIR, appmod.MODEL_DIR, state, backend=os.environ.get("SCORER_BACKEND", "auto"), log=lambda *a: None)
    eng = mk()
    acc = Accounts(users)
    acc.ensure_admin("admin@test.org", "adminpass123")
    app = appmod.create_app(eng, acc, secret="test-secret")
    anon, fam, fam2, auth, adm = (app.test_client() for _ in range(5))

    def login(c, email, pw, role):
        return c.post("/api/auth/login", json={"email": email, "password": pw, "role": role})

    # ---------------------------------------------------------------- basics
    r = anon.get("/api/health").get_json()
    check("health ok", r["ok"] and r["reports"] > 300 and r["found_people"] > 500 and r["admin_exists"], r)
    pl = anon.get("/api/places").get_json()
    check("places is a plain list of names", isinstance(pl, list) and len(pl) == 25 and isinstance(pl[0], str))
    check("api 404 is json", anon.get("/api/nope").get_json() == {"error": "Not found."})
    check("front end: home page", anon.get("/").data == b"home")
    check("front end: subfolder index", anon.get("/family/").data == b"fam" and anon.get("/family/index.html").data == b"fam")
    check("front end: subfolder file", anon.get("/family/family.js").data == b"js")
    check("front end: no path tricks", anon.get("/..%2f..%2fetc/passwd").status_code == 404 and anon.get("/family/nothing.js").status_code == 404)

    # ---------------------------------------------------------------- family accounts
    check("report needs a family login", anon.post("/api/missing", json={}).status_code == 401)
    r = fam.post("/api/auth/signup", json={"name": "Fam One", "email": "Fam1@Test.org", "phone": "555", "password": "password1"})
    check("family signup works", r.status_code == 201 and r.get_json()["user"] == {"email": "fam1@test.org", "name": "Fam One", "role": "family"}, r.get_json())
    check("signup sets a safe cookie", "HttpOnly" in r.headers.get("Set-Cookie", "") and "SameSite=Lax" in r.headers.get("Set-Cookie", ""))
    check("duplicate email is 409", anon.post("/api/auth/signup", json={"name": "x", "email": "fam1@test.org", "password": "password1"}).status_code == 409)
    check("short password is 400", anon.post("/api/auth/signup", json={"name": "x", "email": "a@b.org", "password": "short"}).status_code == 400)
    check("bad email is 400", anon.post("/api/auth/signup", json={"name": "x", "email": "nope", "password": "password1"}).status_code == 400)
    check("me works when logged in", fam.get("/api/auth/me").get_json()["user"]["email"] == "fam1@test.org")
    check("me is 401 when not", anon.get("/api/auth/me").status_code == 401)
    fam.post("/api/auth/logout")
    check("logout ends the session", fam.get("/api/auth/me").status_code == 401)
    check("wrong password is 401", login(fam, "fam1@test.org", "wrongwrong", "family").status_code == 401)
    check("family cannot log in on staff side", login(anon, "fam1@test.org", "password1", "authority").status_code == 401)
    check("family login works", login(fam, "fam1@test.org", "password1", "family").status_code == 200)
    fam2.post("/api/auth/signup", json={"name": "Fam Two", "email": "fam2@test.org", "password": "password2"})
    for _ in range(10):
        login(anon, "ghost@test.org", "whatever1", "family")
    check("repeated failed logins get throttled", login(anon, "ghost@test.org", "whatever1", "family").status_code == 429)

    # ---------------------------------------------------------------- authority requests and admin
    req = {"name": "Officer Lee", "email": "lee@agency.org", "agency": "City Desk", "position": "Officer", "staff_id": "S-1",
           "reason": "Reviewing matches", "password": "officerpass1"}
    check("authority request is pending", anon.post("/api/auth/authority/request", json=req).get_json() == {"status": "pending"})
    check("duplicate request is 409", anon.post("/api/auth/authority/request", json=req).status_code == 409)
    r = login(anon, "lee@agency.org", "officerpass1", "authority")
    check("pending authority gets 403 with a clear message", r.status_code == 403 and "waiting" in r.get_json()["error"], r.get_json())
    check("pending cannot log in as family", login(anon, "lee@agency.org", "officerpass1", "family").status_code == 401)
    check("admin can log in on the staff side", login(adm, "admin@test.org", "adminpass123", "authority").status_code == 200)
    check("admin routes need admin", anon.get("/api/admin/requests").status_code == 401 and fam.get("/api/admin/requests").status_code == 403)
    rq = adm.get("/api/admin/requests").get_json()
    check("admin sees the pending request", len(rq) == 1 and rq[0]["email"] == "lee@agency.org" and "pw" not in rq[0], rq)
    check("approve works", adm.post("/api/admin/requests/lee@agency.org/approve").status_code == 200)
    check("approve twice is 404", adm.post("/api/admin/requests/lee@agency.org/approve").status_code == 404)
    check("approved authority can log in", login(auth, "lee@agency.org", "officerpass1", "authority").status_code == 200)
    anon.post("/api/auth/authority/request", json=dict(req, email="no@agency.org"))
    check("reject removes the request", adm.post("/api/admin/requests/no@agency.org/reject").status_code == 200 and not adm.get("/api/admin/requests").get_json())
    check("rejected person cannot log in", login(anon, "no@agency.org", "officerpass1", "authority").status_code == 401)
    r = adm.post("/api/admin/authorities", json={"name": "Desk", "email": "desk@agency.org", "password": "deskpass123"})
    check("admin can create an authority", r.status_code == 201 and r.get_json()["role"] == "authority", r.get_json())
    check("authority list shows authority and admin", {u["role"] for u in adm.get("/api/admin/authorities").get_json()} == {"authority", "admin"})
    check("authority cannot use admin routes", auth.get("/api/admin/authorities").status_code == 403)
    check("admin cannot be removed", adm.delete("/api/admin/authorities/admin@test.org").status_code == 403)
    check("authority can be removed", adm.delete("/api/admin/authorities/desk@agency.org").status_code == 200)
    check("removed authority cannot log in", login(anon, "desk@agency.org", "deskpass123", "authority").status_code == 401)

    # ---------------------------------------------------------------- authority access: staff login only (no PIN)
    check("authority routes need a login", anon.get("/api/missing").status_code == 401)
    check("a PIN header alone grants nothing", anon.get("/api/missing", headers=H).status_code == 401)
    check("a family login is not enough", fam.get("/api/missing").status_code == 401)
    rows = auth.get("/api/missing").get_json()
    need = {"id", "age_min", "gender", "last_seen_place", "last_seen_time", "contact", "status", "summary", "flagged"}
    check("authority list is an array of full records", isinstance(rows, list) and len(rows) == len(eng.mdf) and need <= set(rows[0]), list(rows[0]))
    check("matches needs a staff login", anon.get("/api/matches/M1").status_code == 401)
    check("found needs a staff login", anon.post("/api/found", json={}).status_code == 401)
    check("admin works as authority too", adm.get("/api/missing").status_code == 200)

    # ---------------------------------------------------------------- family members and reports
    check("bad report rejected (no age)", fam.post("/api/missing", json={"gender": "male"}).status_code == 400)
    check("bad report rejected (no time)", fam.post("/api/missing", json={"age_min": 5, "age_max": 7, "last_seen_place": "Fish Market"}).status_code == 400)
    check("non-json rejected", fam.post("/api/missing", data="x", content_type="text/plain").status_code == 400)
    r = fam.post("/api/family/members", json={"name": "Aunt Rosa", "relationship": "aunt", "age": 54, "gender": "female", "height_cm": 160})
    pid = r.get_json()["id"]
    check("family can add a member", r.status_code == 201 and pid.startswith("P"), r.get_json())
    check("member needs a name", fam.post("/api/family/members", json={"age": 5}).status_code == 400)
    check("other family sees no members", fam2.get("/api/family/members").get_json() == [])
    check("other family cannot delete it", fam2.delete(f"/api/family/members/{pid}").status_code == 404)
    check("authority cannot use family routes", auth.get("/api/family/members").status_code == 403)

    cases = anon.get("/api/demo-cases").get_json()
    check("demo cases are a list with id and title", isinstance(cases, list) and len(cases) == 5 and all(x["id"] and x["title"] for x in cases))
    check("demo cases say how they behave", all("status_when_submitted" in x and "good_for_live_demo" in x for x in cases))
    good = [x for x in cases if x["good_for_live_demo"]]
    print("     demo cases good for a live demo:", len(good), "of", len(cases))
    case = (good or cases)[0]
    check("report with someone else's member id is rejected", fam2.post("/api/missing", json=dict(case["missing"], member_id=pid)).status_code == 400)
    r = fam.post("/api/missing", json=dict(case["missing"], member_id=pid))
    check("family can submit a report", r.status_code == 201 and r.get_json()["id"].startswith("M") and r.get_json()["status"] in ("searching", "possible_match"), r.get_json())
    mid = r.get_json()["id"]
    mem = fam.get("/api/family/members").get_json()[0]
    check("member is linked to the report", mem["report_id"] == mid and mem["status"] in ("searching", "possible_match"), mem)
    fr = fam.get("/api/family/reports").get_json()
    check("family sees its own reports", len(fr) == 1 and fr[0]["id"] == mid and fr[0]["member_name"] == "Aunt Rosa"
          and {"status", "last_seen_place", "last_seen_time"} <= set(fr[0]), fr)
    check("other family sees none", fam2.get("/api/family/reports").get_json() == [])
    s = anon.get(f"/api/status/{mid}").get_json()
    check("status shows only status and contact line", set(s) == {"id", "status", "message", "authority_contact"} and s["authority_contact"], s)
    check("status starts as expected", s["status"] == ("searching" if good else "possible_match"))
    check("unknown id is 404", anon.get("/api/status/M99999").status_code == 404)

    # ---------------------------------------------------------------- found people, matching, decisions
    r = auth.post("/api/found", json=case["found"])
    check("authority can add a found person", r.status_code == 201 and r.get_json()["id"].startswith("F"), r.get_json())
    fid = r.get_json()["id"]
    m = auth.get(f"/api/matches/{mid}").get_json()
    ids = [x["found_id"] for x in m["candidates"]]
    check("matches has missing_id, missing, candidates", m["missing_id"] == mid and m["missing"]["contact"] and len(ids) == 10)
    check("true match is in the top 5", fid in ids[:5], ids[:5])
    top = m["candidates"][0]
    need = {"found_id", "score", "reasons", "found", "decision", "claimed_by"}
    check("candidate has the agreed fields", need <= set(top) and 0 <= top["score"] <= 99 and top["reasons"]
          and {"age_min", "age_max", "gender", "clothing", "marks", "found_place", "found_time", "current_location", "source"} <= set(top["found"]), set(top))
    check("reasons have label+matched", all({"label", "matched"} == set(x) for x in top["reasons"]))
    check("authority-entered people have source authority", top["found"]["source"] == "authority")
    check("scores are in descending order", [x["score"] for x in m["candidates"]] == sorted((x["score"] for x in m["candidates"]), reverse=True))
    check("status flips to possible match", anon.get(f"/api/status/{mid}").get_json()["status"] == "possible_match")
    flagged = [x for x in auth.get("/api/missing").get_json() if x["id"] == mid][0]
    check("report is flagged in the authority list", flagged["flagged"] is True and flagged["status"] == "possible_match")

    D = lambda c, m_, f_, d_: c.post(f"/api/matches/{m_}/decision", json={"found_id": f_, "decision": d_})
    r = D(auth, mid, fid, "confirm")
    check("confirm works", r.status_code == 200 and r.get_json()["status"] == "reunited", r.get_json())
    check("family sees reunited", anon.get(f"/api/status/{mid}").get_json()["status"] == "reunited")
    check("family list shows reunited", fam.get("/api/family/reports").get_json()[0]["status"] == "reunited")
    m2 = auth.get(f"/api/matches/{mid}").get_json()
    check("confirmed match listed first", m2["candidates"][0]["found_id"] == fid and m2["candidates"][0]["decision"] == "confirmed")
    other_cand = m2["candidates"][1]["found_id"]
    r = D(auth, mid, other_cand, "confirm")
    check("second confirm on the same report is 409 (undo first)", r.status_code == 409 and "Undo" in r.get_json()["error"], r.get_json())

    other = next(x["id"] for x in rows if x["id"] != mid)
    r = D(auth, other, fid, "confirm")
    check("cannot confirm an already-claimed person", r.status_code == 409 and r.get_json()["error"], r.get_json())
    m3 = auth.get(f"/api/matches/{other}").get_json()
    cf = [x for x in m3["candidates"] if x["found_id"] == fid]
    if not cf:                                                  # make sure we look at a list that contains the claimed person
        eng.S[eng._index(other), list(eng.fdf["id"]).index(fid)] = 0.999
        m3 = auth.get(f"/api/matches/{other}").get_json()
        cf = [x for x in m3["candidates"] if x["found_id"] == fid]
    check("claimed person stays listed and shows claimed_by", cf and cf[0]["claimed_by"] == mid, cf)
    check("claimed_by is null for the owner", m2["candidates"][0]["claimed_by"] is None)

    cand = next(x["found_id"] for x in m3["candidates"] if x["found_id"] != fid)
    D(auth, other, cand, "reject")
    m4 = auth.get(f"/api/matches/{other}").get_json()
    check("rejected candidate stays in the list, marked", [x["decision"] for x in m4["candidates"] if x["found_id"] == cand] == ["rejected"])
    D(auth, other, cand, "undo")
    m5 = auth.get(f"/api/matches/{other}").get_json()
    check("undo clears the decision", [x["decision"] for x in m5["candidates"] if x["found_id"] == cand] == [None])
    D(auth, mid, fid, "undo")
    check("undo of a confirm goes back to possible match", anon.get(f"/api/status/{mid}").get_json()["status"] == "possible_match")
    check("bad decision value", D(auth, other, cand, "maybe").status_code == 400)
    check("unknown found id", D(auth, other, "F99999", "reject").status_code == 404)
    check("unknown report id", D(auth, "M99999", cand, "reject").status_code == 404)

    # ---------------------------------------------------------------- public found reports
    pub = dict(case["found"], reporter_name="Kind Stranger", reporter_phone="555-1234")
    r = anon.post("/api/public/found", json=pub)
    check("public can report a found person", r.status_code == 201 and set(r.get_json()) == {"id"}, r.get_json())
    pid_f = r.get_json()["id"]
    eng.S[eng._index(other), list(eng.fdf["id"]).index(pid_f)] = 0.999
    m6 = auth.get(f"/api/matches/{other}").get_json()
    pc = [x for x in m6["candidates"] if x["found_id"] == pid_f]
    check("public reports are labelled source public", pc and pc[0]["found"]["source"] == "public" and pc[0]["found"]["reporter_phone"] == "555-1234", pc)
    check("public report with bad data is 400", anon.post("/api/public/found", json={"gender": "male"}).status_code == 400)
    check("nothing about reporters reaches families", "Kind Stranger" not in str(anon.get(f"/api/status/{mid}").get_json()) + str(fam.get("/api/family/reports").get_json()))

    # ---------------------------------------------------------------- persistence
    n_m, n_f = len(eng.mdf), len(eng.fdf)
    eng2 = mk()
    check("state survives a restart", len(eng2.mdf) == n_m and len(eng2.fdf) == n_f and eng2.status(other) in ("searching", "possible_match"))
    check("public source survives a restart", eng2.fdf[eng2.fdf["id"] == pid_f]["source"].iloc[0] == "public")
    acc2 = Accounts(users)
    check("accounts survive a restart", acc2.authenticate("fam1@test.org", "password1", "family")["role"] == "family" and acc2.family_reports("fam1@test.org"))
    check("passwords are not stored in plain text", b"password1" not in open(users, "rb").read())
    check("family can delete a member", fam.delete(f"/api/family/members/{pid}").status_code == 200 and fam.get("/api/family/members").get_json() == [])

    # ---------------------------------------------------------------- encryption at rest
    try:
        import cryptography  # noqa: F401
        have_crypto = True
    except ImportError:
        have_crypto = False
    if have_crypto:
        os.environ["STATE_KEY"] = "a test passphrase"
        enc_state, enc_users = os.path.join(tmp, "enc_state.json"), os.path.join(tmp, "enc_users.json")
        e3 = Engine(appmod.DATA_DIR, appmod.MODEL_DIR, enc_state, backend="numpy", log=lambda *a: None)
        e3.add_missing(case["missing"])
        from store import state_key
        Accounts(enc_users, state_key()).signup_family("Enc", "enc@test.org", "555", "password1")
        raw, raw_u = open(enc_state, "rb").read(), open(enc_users, "rb").read()
        check("encrypted state file has the magic header", raw[:4] == b"RAI1" and raw_u[:4] == b"RAI1")
        check("encrypted files contain no readable text", case["missing"]["contact"].encode() not in raw and b"enc@test.org" not in raw_u)
        e4 = Engine(appmod.DATA_DIR, appmod.MODEL_DIR, enc_state, backend="numpy", log=lambda *a: None)
        check("encrypted state loads with the right key", len(e4.mdf) == len(e3.mdf))
        os.environ["STATE_KEY"] = "wrong passphrase"
        try:
            Engine(appmod.DATA_DIR, appmod.MODEL_DIR, enc_state, backend="numpy", log=lambda *a: None)
            check("wrong key is refused", False)
        except Exception:
            check("wrong key is refused", True)
        os.environ.pop("STATE_KEY")
    else:
        print("SKIP encryption tests (pip install cryptography to enable)")

    # ---------------------------------------------------------------- misc
    body = dict(case["missing"], last_seen_place="Somewhere not on the list")
    r = fam.post("/api/missing", json=body)
    check("unknown place accepted", r.status_code == 201 and r.get_json()["place_recognised"] is False, r.get_json())
    r = auth.post("/api/rescan").get_json()
    check("rescan reports timing", r["pairs"] > 100000 and r["scoring_seconds"] >= 0, r)
    b = anon.get("/api/benchmark").get_json()
    check("benchmark has live + quality", "live_rescan" in b and "quality" in b and "scorer" in b)
    check("benchmark has the front end's keys", b["accuracy"]["engine"]["top1"] > 0 and "top5" in b["accuracy"]["keyword"]
          and b["accuracy"]["cases"] > 50 and b["speed"]["pairs"] > 0 and b["speed"]["full_rescan_seconds"] >= 0 and b["note"], b.get("accuracy"))
    check("chip section absent until measured", "chip" not in b or b["chip"].get("note"))

    # chip section when both benchmark files exist (copy of the models folder, so nothing real is touched)
    import json
    import shutil
    mdir = os.path.join(tmp, "models_copy")
    shutil.copytree(appmod.MODEL_DIR, mdir)
    json.dump({"chip_on": {"pairs_per_sec": 200000, "seconds": 0.8}, "chip_off": {"pairs_per_sec": 40000, "seconds": 4.0},
               "note": "4-layer test."}, open(os.path.join(mdir, "benchmark.json"), "w"))
    json.dump({"pairs_scored": 2000000, "layers": [[33, 1]], "numpy_cpu": {"rows_per_sec": 50000000},
               "chip_on": {"pairs_per_sec": 13000000, "seconds": 0.15}, "chip_off": {"pairs_per_sec": 22000000, "seconds": 0.09},
               "speedup_on_vs_off": 0.6, "interpretation": "The accelerator was slower (0.60x) for this tiny model."},
              open(os.path.join(mdir, "benchmark_scorer.json"), "w"))
    old_dir, appmod.MODEL_DIR = appmod.MODEL_DIR, mdir
    try:
        b2 = appmod.create_app(eng, acc).test_client().get("/api/benchmark").get_json()
    finally:
        appmod.MODEL_DIR = old_dir
    ch = b2.get("chip", {})
    check("chip section shows the stress test, labelled", ch.get("speedup_on_vs_off") == 5.0 and "NOT our matcher" in ch.get("note", "")
          and ch["on"]["seconds"] == 0.8 and ch["off"]["seconds"] == 4.0, ch)
    check("chip section also reports the deployed scorer honestly", ch.get("deployed_scorer", {}).get("speedup_on_vs_off") == 0.6
          and "slower" in ch["note"] and "chip_on" not in b2, ch.get("deployed_scorer"))

    # ---------------------------------------------------------------- language-model chip results (chip_models.json)
    json.dump({"minilm": {"model": "all-MiniLM-L6-v2", "texts": 1000, "speedup_median": 9.4, "chip_median": 3.0, "cpu_median": 28.2,
                          "output_agreement": {"cosine_similarity_min": 0.9999}},
               "granite": {"model": "granite-4.0-350m", "speedup_median": 6.9, "identical_answers": "5 of 5"}},
              open(os.path.join(mdir, "chip_models.json"), "w"))
    appmod.MODEL_DIR = mdir
    try:
        b3 = appmod.create_app(eng, acc).test_client().get("/api/benchmark").get_json()
    finally:
        appmod.MODEL_DIR = old_dir
    lm = b3.get("chip", {}).get("language_models", {})
    check("chip section includes the language-model results", lm.get("minilm", {}).get("speedup_median") == 9.4
          and lm.get("granite", {}).get("identical_answers") == "5 of 5" and "minilm on the accelerator" in b3["chip"]["note"], b3.get("chip"))

    # ---------------------------------------------------------------- reading boxes from the description
    h = anon.get("/api/health").get_json()
    check("health reports the extractor", h.get("extraction", {}).get("regex") is True and h["extraction"]["granite"] == "off", h.get("extraction"))
    text_only = {"age_min": 8, "age_max": 10, "gender": "male", "last_seen_place": "Fish Market", "last_seen_time": "2026-10-16T18:00",
                 "description": "My son, 9, was last seen near Fish Market, wearing a red hoodie and blue jeans. Has short curly brown hair. "
                                "Distinguishing marks: mole on left cheek."}
    r = fam.post("/api/missing", json=text_only)
    check("text-only report is accepted", r.status_code == 201, r.get_json())
    rec = [x for x in auth.get("/api/missing").get_json() if x["id"] == r.get_json()["id"]][0]
    check("empty boxes are read from the description",
          "brown" in rec["hair"] and "hoodie" in rec["clothing"] and "jeans" in rec["clothing"] and "mole" in rec["marks"], rec)
    check("auto-filled boxes are tagged", set(rec["auto_filled"].split(",")) == {"hair", "clothing", "marks"}, rec["auto_filled"])
    typed = dict(text_only, hair="black", clothing="green coat", marks="scar on chin")
    r = fam.post("/api/missing", json=typed)
    rec2 = [x for x in auth.get("/api/missing").get_json() if x["id"] == r.get_json()["id"]][0]
    check("typed boxes are never overwritten", (rec2["hair"], rec2["clothing"], rec2["marks"]) == ("black", "green coat", "scar on chin")
          and not rec2["auto_filled"], rec2)
    r = fam.post("/api/missing", json={k: v for k, v in text_only.items() if k != "description"})
    rec3 = [x for x in auth.get("/api/missing").get_json() if x["id"] == r.get_json()["id"]][0]
    check("no description, nothing invented", not (rec3["hair"] or rec3["clothing"] or rec3["marks"]) and not rec3["auto_filled"], rec3)
    r = auth.post("/api/found", json={"age_min": 8, "age_max": 11, "gender": "male", "found_place": "Fish Market", "found_time": "2026-10-16T20:00",
                                      "description": "Boy found near the market, wearing red hoodie. Hair: short brown."})
    check("found record also reads the description", r.status_code == 201, r.get_json())
    state_after = mk()                                           # restart: auto_filled must survive a save and reload
    again = state_after.list_missing()
    check("auto-filled tags survive a restart", any(x["auto_filled"] for x in again if x["id"] == rec["id"]))

    # ---------------------------------------------------------------- extraction module on its own
    import extract as X
    check("regex reads hair, clothing and marks", X.regex_extract("Girl abt 12, parka (maroon), specs. Hair: short black.")
          == {"hair": "short black", "clothing": ["parka (maroon)"], "marks": ["specs"]}, X.regex_extract("Girl abt 12, parka (maroon), specs. Hair: short black."))
    check("regex copes with a typo in 'hair'", X.regex_hair("Has short grey hari.") == "short grey")
    check("regex finds nothing when nothing is there", X.regex_extract("My brother, 31, was last seen near Ferry Bridge. Please help.")
          == {"hair": None, "clothing": [], "marks": []})
    g = {"hair": "short silver", "clothing": ["navy coat", "parka (maroon)"], "marks": ["mole on left cheek", "specs"]}
    got = X.combine(X.regex_extract("Girl abt 12, parka (maroon), specs. Hair: short black."), g, "Girl abt 12, parka (maroon), specs. Hair: short black.")
    check("grounding check drops invented details", got == {"hair": "short black", "clothing": ["parka (maroon)"], "marks": ["specs"]}, got)
    check("model output is parsed safely", X.parse_model_json("no json here") == {"hair": None, "clothing": [], "marks": []}
          and X.parse_model_json('x {"hair": "a", "clothing": "red hat", "marks": []}')["clothing"] == ["red hat"])
    import features as FTm
    check("wider vocabulary: hair, clothing, marks",
          FTm.parse_hair("cropped short golden")[1] == 2.0 and FTm.parse_hair("ponytail raven")[0] == 0.0
          and FTm.parse_clothing("dupatta (teal), salmon-coloured knitwear") == [("blue", "neckwear", "neckwear"), ("pink", "knit", "sweater")]
          and [m[0] for m in FTm.parse_marks("cut mark through left brow")] == ["scar"]
          and FTm.parse_marks("drags right leg") == [("mobility", "leg", "right")])


    # ---------------------------------------------------------------- explanations agree with the score
    import pandas as pd
    import features as FTx
    mrec = {"id": "x", "age_min": 61, "age_max": 62, "gender": "female", "height_cm": None, "hair": "long black hair",
            "clothing": "tan rain jacket, navy slacks, bright orange running shoes", "marks": "uses a walking stick",
            "last_seen_place": "Iron Bridge", "last_seen_time": "2026-10-15T10:00", "description": "", "contact": ""}
    frec = {"id": "y", "age_min": 58, "age_max": 61, "gender": "female", "height_cm": None, "hair": "shoulder length jet black",
            "clothing": "gray rain jacket, brown skirt, navy sandals", "marks": "", "found_place": "East Embankment",
            "found_time": "2026-10-17T15:00", "current_location": "", "description": ""}
    Xp = FTx.pair_tensor(FTx.build_side(pd.DataFrame([mrec]), "missing", eng.art), FTx.build_side(pd.DataFrame([frec]), "found", eng.art))[0, 0]
    rs = {r["label"].split()[0]: r for r in FTx.reasons(mrec, frec, Xp)}
    check("weak hair overlap is a dash, not a tick", "partly similar" in rs["Hair"]["label"] and rs["Hair"]["matched"] is False, rs["Hair"])
    check("weak clothing overlap is a dash, not a tick", "only partly" in rs["Clothing"]["label"] and rs["Clothing"]["matched"] is False, rs["Clothing"])
    frec2 = dict(frec, hair="long black hair", clothing="tan rain jacket, navy slacks, orange running shoes", marks="walking stick")
    X2 = FTx.pair_tensor(FTx.build_side(pd.DataFrame([mrec]), "missing", eng.art), FTx.build_side(pd.DataFrame([frec2]), "found", eng.art))[0, 0]
    rs2 = {r["label"].split()[0]: r for r in FTx.reasons(mrec, frec2, X2)}
    check("a real overlap still gets ticks", rs2["Hair"]["matched"] and rs2["Clothing"]["matched"] and rs2["Distinguishing"]["matched"], rs2)

    # ---------------------------------------------------------------- empty start (PRELOAD=none) and reset_demo.py
    empty_state = os.path.join(tmp, "empty", "state.json")
    os.makedirs(os.path.dirname(empty_state))
    e0 = Engine(appmod.DATA_DIR, appmod.MODEL_DIR, empty_state, backend="numpy", log=lambda *a: None, preload="none")
    check("PRELOAD=none starts with nothing", len(e0.mdf) == 0 and len(e0.fdf) == 0 and e0.list_missing() == [] and e0.S.shape == (0, 0))
    check("demo cases work on an empty system", len(e0.get_demo_cases()) == 5 and all(c["status_when_submitted"] == "searching" for c in e0.get_demo_cases()))
    check("benchmark works on an empty system", "quality" in e0.benchmark("") and e0.benchmark("")["live_rescan"]["pairs"] == 0)
    dc = [c for c, x in zip(eng.demo_cases, cases) if x["true_match_score"] >= 90][0]
    r1 = e0.add_missing(dc["missing"])
    check("first report on an empty system gets id M1 and status searching", r1["id"] == "M1" and r1["status"] == "searching", r1)
    check("a report with nobody to compare against has no candidates", e0.matches("M1")["candidates"] == [])
    r2 = e0.add_found(dc["found"])
    check("found person is F1 and flags the report", r2["id"] == "F1" and r2["flagged_reports"] == 1, r2)
    check("status flips to possible_match", e0.status("M1") == "possible_match")
    m0 = e0.matches("M1")
    check("one candidate, with reasons", len(m0["candidates"]) == 1 and m0["candidates"][0]["score"] >= 90 and m0["candidates"][0]["reasons"])
    e0.decide("M1", "F1", "confirm")
    e1 = Engine(appmod.DATA_DIR, appmod.MODEL_DIR, empty_state, backend="numpy", log=lambda *a: None, preload="none")
    check("empty-start data survives a restart", e1.status("M1") == "reunited" and len(e1.fdf) == 1)
    try:
        Engine(appmod.DATA_DIR, appmod.MODEL_DIR, empty_state, log=lambda *a: None, preload="some")
        check("bad PRELOAD value is rejected", False)
    except ValueError:
        check("bad PRELOAD value is rejected", True)

    import subprocess
    rdir = os.path.join(tmp, "reset")
    os.makedirs(rdir)
    rstate, rusers = os.path.join(rdir, "state.json"), os.path.join(rdir, "users.json")
    shutil.copy(empty_state, rstate)
    ra = Accounts(rusers)
    ra.ensure_admin("boss@test.org", "bosspass123")
    ra.signup_family("F", "f@test.org", "1", "password1")
    ra.add_member("f@test.org", {"name": "Rosa", "age": 50})
    env = dict(os.environ, STATE_PATH=rstate, ACCOUNTS_PATH=rusers)
    out = subprocess.run([sys.executable, os.path.join(HERE, "reset_demo.py")], env=env, capture_output=True, text=True)
    ra2 = Accounts(rusers)
    check("reset_demo clears reports but keeps accounts by default", out.returncode == 0 and not os.path.exists(rstate)
          and "f@test.org" in ra2.d["users"] and ra2.d["members"] == {}, out.stdout + out.stderr)
    out = subprocess.run([sys.executable, os.path.join(HERE, "reset_demo.py"), "--accounts"], env=env, capture_output=True, text=True)
    ra3 = Accounts(rusers)
    check("reset_demo --accounts removes families but keeps the admin", set(ra3.d["users"]) == {"boss@test.org"}, out.stdout + out.stderr)
    check("reset_demo keeps a backup", any(n.startswith("backup_") for n in os.listdir(rdir)))

    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
