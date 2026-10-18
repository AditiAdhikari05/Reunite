"""
app.py - Flask web app: serves the front end and the JSON API (see README.md).

Run:   python app.py            (listens on 0.0.0.0:5000)
Settings (environment variables, all optional):
  ADMIN_EMAIL, ADMIN_PASSWORD   creates/updates the admin account at start-up (or run create_admin.py)
  SECRET_KEY     signs login cookies                            default: random key saved in ./state/secret.key
  COOKIE_SECURE  1 when the site is served over HTTPS
  AUTHORITY_CONTACT  contact line families see on the status page
  DATA_DIR       folder with missing.csv, found.csv, places.csv default: ../data
  MODEL_DIR      folder written by train.py                     default: ./models
  FRONTEND_DIR   folder with index.html etc.                    default: ../frontend, ./frontend, then a placeholder
  STATE_PATH     where new reports/decisions are saved          default: ./state/state.json
  ACCOUNTS_PATH  where user accounts are saved                  default: next to STATE_PATH, users.json
  SCORER_BACKEND auto | numpy | tf                              default: auto
  STATE_KEY      passphrase: encrypts saved data with AES-256-GCM (needs: pip install cryptography)
  NNPA_DEVICES=0 forces TensorFlow onto the plain CPU (for on/off comparisons)
"""
import json
import os
import secrets
import sys
import threading
import time
from collections import defaultdict, deque
from functools import wraps

from flask import Flask, jsonify, request, send_from_directory, session
from werkzeug.security import safe_join

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from accounts import Accounts, AuthFailed, Conflict, Forbidden  # noqa: E402
from engine import Engine  # noqa: E402
from store import state_key  # noqa: E402

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(HERE, "..", "data"))
MODEL_DIR = os.environ.get("MODEL_DIR", os.path.join(HERE, "models"))
STATE_PATH = os.environ.get("STATE_PATH", os.path.join(HERE, "state", "state.json"))
ACCOUNTS_PATH = os.environ.get("ACCOUNTS_PATH", os.path.join(os.path.dirname(os.path.abspath(STATE_PATH)), "users.json"))
CONTACT = os.environ.get("AUTHORITY_CONTACT", "Reunification Desk, phone 555-0199 (demo number)")

FALLBACK_PAGE = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Reunite AI backend</title><body style="font-family:system-ui;max-width:40rem;margin:3rem auto;padding:0 1rem">
<h1>Backend is running</h1><p>No front end was found. Put the <code>frontend</code> folder (with <code>index.html</code>)
next to the <code>backend</code> folder, or set <code>FRONTEND_DIR</code>. You do not need to restart: it is picked up on the next page load.</p>
<p><a href="/api/health">/api/health</a> &middot; <a href="/api/benchmark">/api/benchmark</a></p></body>"""


def find_frontend():
    cands = [os.environ.get("FRONTEND_DIR"), os.path.join(HERE, "..", "frontend"), os.path.join(HERE, "frontend"),
             os.path.join(HERE, "frontend_placeholder")]
    for c in cands:
        if c and os.path.exists(os.path.join(c, "index.html")):
            return os.path.abspath(c)
    return None


def _secret():
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    path = os.path.join(os.path.dirname(os.path.abspath(STATE_PATH)), "secret.key")
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(secrets.token_hex(32))
    return open(path).read().strip()


class Throttle:
    """Allows at most `limit` hits per `window` seconds for each key (in memory, per process)."""
    def __init__(self):
        self.hits, self.lock = defaultdict(deque), threading.Lock()

    def hit(self, key, limit, window):
        now = time.time()
        with self.lock:
            q = self.hits[key]
            while q and q[0] < now - window:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True

    def count(self, key, window):
        now = time.time()
        with self.lock:
            return sum(1 for t in self.hits[key] if t >= now - window)


def create_app(engine=None, accounts=None, secret=None):
    app = Flask(__name__, static_folder=None)
    app.config.update(MAX_CONTENT_LENGTH=64 * 1024, SECRET_KEY=secret or _secret(),
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                      SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE") == "1",
                      PERMANENT_SESSION_LIFETIME=12 * 3600)
    key = state_key()
    eng = engine or Engine(DATA_DIR, MODEL_DIR, STATE_PATH, backend=os.environ.get("SCORER_BACKEND", "auto"))
    acc = accounts or Accounts(ACCOUNTS_PATH, key)
    if os.environ.get("ADMIN_EMAIL") and os.environ.get("ADMIN_PASSWORD"):
        acc.ensure_admin(os.environ["ADMIN_EMAIL"], os.environ["ADMIN_PASSWORD"])
    thr = Throttle()
    bench_paths = [os.path.join(MODEL_DIR, "benchmark.json"), os.path.join(HERE, "benchmark.json"),     # most specific file first
                   os.path.join(HERE, "..", "benchmark.json")]
    scorer_bench = os.path.join(MODEL_DIR, "benchmark_scorer.json")

    def err(msg, code):
        return jsonify({"error": msg}), code

    def body_json():
        b = request.get_json(silent=True)
        return b if isinstance(b, dict) else None

    def ip():
        return request.remote_addr or "?"

    def current_user():
        email = session.get("email")
        return acc.get(email) if email else None            # looked up every time, so removed/changed accounts lose access at once

    # ---- access checks. Each returns an error response, or None when access is fine.
    def need_family():
        u = current_user()
        if not u:
            return err("Please log in to continue.", 401)
        if u["role"] != "family":
            return err("This page is for family accounts.", 403)
        return None

    def need_admin():
        u = current_user()
        if not u:
            return err("Please log in to continue.", 401)
        if u["role"] != "admin":
            return err("Only an administrator can do this.", 403)
        return None

    def need_authority():
        u = current_user()
        if not u or u["role"] not in ("authority", "admin"):
            return err("Please log in with an authority account.", 401)
        return None

    def guarded(check):
        def deco(fn):
            @wraps(fn)
            def wrapper(*a, **k):
                bad = check()
                return bad if bad else fn(*a, **k)
            return wrapper
        return deco

    @app.after_request
    def headers(r):
        r.headers["X-Content-Type-Options"] = "nosniff"
        if request.path.startswith("/api/"):
            r.headers["Cache-Control"] = "no-store"
        elif r.mimetype in ("text/html", "text/css", "application/javascript", "text/javascript"):
            r.headers["Cache-Control"] = "no-cache"          # so Aditi's updates show up straight away
        return r

    @app.errorhandler(404)
    def e404(_):
        return err("Not found.", 404) if request.path.startswith("/api/") else ("Not found", 404)

    @app.errorhandler(405)
    def e405(_):
        return err("Method not allowed.", 405)

    @app.errorhandler(413)
    def e413(_):
        return err("Request too large.", 413)

    @app.errorhandler(500)
    def e500(_):
        return err("Something went wrong on the server. Please try again.", 500)

    # ------------------------------------------------------------------ public
    @app.get("/api/health")
    def health():
        return jsonify({"ok": True, "reports": len(eng.mdf), "found_people": len(eng.fdf), "scorer": eng.scorer.info(),
                        "frontend": bool(find_frontend()), "state_encrypted": bool(eng.key),
                        "extraction": eng.extractor.info(), "preload": eng.preload,
                        "admin_exists": any(u["role"] == "admin" for u in acc.d["users"].values())})

    @app.get("/api/places")
    def places():
        return jsonify(list(eng.places["place"]))

    @app.get("/api/status/<mid>")
    def status(mid):
        s = eng.public_status(mid)
        if not s:
            return err("No report with that ID.", 404)
        s["authority_contact"] = CONTACT                      # nothing else about the case is ever returned here
        return jsonify(s)

    @app.get("/api/benchmark")
    def benchmark():
        paths = [p for p in bench_paths if os.path.exists(p)]
        stress = json.load(open(paths[0])) if paths else {}          # generic neural-network test, saved from the notebook
        out = eng.benchmark(paths[0] if paths else "")
        for k in ("chip_on", "chip_off"):                             # re-labelled below so they cannot be mistaken for the matcher
            out.pop(k, None)
        sb = json.load(open(scorer_bench)) if os.path.exists(scorer_bench) else {}
        if sb:
            out["scorer_benchmark"] = sb
        chip, notes = {}, []
        if "chip_on" in stress and "chip_off" in stress:
            on, off = stress["chip_on"], stress["chip_off"]
            chip = {"on": on, "off": off, "what_was_tested": "a generic 4-layer neural network (not the matcher)"}
            if on.get("pairs_per_sec") and off.get("pairs_per_sec"):
                chip["speedup_on_vs_off"] = round(on["pairs_per_sec"] / off["pairs_per_sec"], 2)
            notes.append("Stress test, measured on this server: " + stress.get("note", "accelerator on vs off.")
                         + " This is a generic neural network used to show when the accelerator helps, NOT our matcher.")
        if "chip_on" in sb and "chip_off" in sb:
            dep = {"accelerator_on_pairs_per_sec": sb["chip_on"]["pairs_per_sec"], "accelerator_off_pairs_per_sec": sb["chip_off"]["pairs_per_sec"],
                   "speedup_on_vs_off": sb.get("speedup_on_vs_off"), "layers": sb.get("layers"), "verdict": sb.get("interpretation", "")}
            if sb.get("numpy_cpu"):
                dep["plain_cpu_numpy_pairs_per_sec"] = sb["numpy_cpu"].get("rows_per_sec")
            chip["deployed_scorer"] = dep
            if "on" not in chip:                                      # no stress test file: the scorer result is all we have
                chip.update({"on": sb["chip_on"], "off": sb["chip_off"], "what_was_tested": "the deployed matcher"})
            notes.append(f"Our deployed matcher, measured by bench_scorer.py on {int(sb.get('pairs_scored', 0)):,} pairs: " + sb.get("interpretation", ""))
        lm_path = os.path.join(MODEL_DIR, "chip_models.json")
        if os.path.exists(lm_path):
            try:
                lm = json.load(open(lm_path))
                if lm.get("minilm") or lm.get("granite"):
                    chip["language_models"] = lm
                    for name in ("minilm", "granite"):
                        r = lm.get(name) or {}
                        if r.get("speedup_median"):
                            notes.append(f"{name} on the accelerator vs CPU: {r['speedup_median']}x faster (median of repeated runs).")
            except (OSError, ValueError):
                pass
        if chip:
            chip["note"] = " ".join(notes)
            out["chip"] = chip
        elif sb.get("numpy_cpu"):
            out["chip"] = {"note": "The accelerator comparison did not complete on this server. See scorer_benchmark for details."}
        return jsonify(out)

    @app.get("/api/demo-cases")
    def demo_cases():
        return jsonify(eng.get_demo_cases())

    @app.post("/api/public/found")
    def public_found():
        if not thr.hit(("pubfound", ip()), 30, 3600):
            return err("Too many reports from this connection. Please try again later.", 429)
        b = body_json()
        if b is None:
            return err("Send a JSON object.", 400)
        try:
            r = eng.add_found(b, source="public")
        except ValueError as e:
            return err(str(e), 400)
        return jsonify({"id": r["id"]}), 201                   # the public never sees match information

    # ------------------------------------------------------------------ accounts
    def login_user(u):
        session.clear()
        session.permanent = True
        session["email"] = u["email"]
        return jsonify({"user": u})

    @app.post("/api/auth/signup")
    def signup():
        if not thr.hit(("signup", ip()), 20, 3600):
            return err("Too many sign-ups from this connection. Please try again later.", 429)
        b = body_json()
        if b is None:
            return err("Send a JSON object.", 400)
        try:
            u = acc.signup_family(b.get("name"), b.get("email"), b.get("phone"), b.get("password"))
        except ValueError as e:
            return err(str(e), 400)
        except Conflict as e:
            return err(str(e), 409)
        return login_user(u), 201

    @app.post("/api/auth/login")
    def login():
        b = body_json()
        if b is None:
            return err("Send a JSON object.", 400)
        email = str(b.get("email", "")).strip().lower()
        if thr.count(("loginfail", email), 300) >= 10 or thr.count(("loginfail", ip()), 300) >= 30:
            return err("Too many failed attempts. Please wait a few minutes and try again.", 429)
        try:
            u = acc.authenticate(email, b.get("password"), str(b.get("role", "family")))
        except Forbidden as e:
            return err(str(e), 403)
        except AuthFailed as e:
            thr.hit(("loginfail", email), 10 ** 6, 300)
            thr.hit(("loginfail", ip()), 10 ** 6, 300)
            return err(str(e), 401)
        return login_user(u)

    @app.post("/api/auth/logout")
    def logout():
        session.clear()
        return jsonify({"ok": True})

    @app.get("/api/auth/me")
    def me():
        u = current_user()
        return jsonify({"user": u}) if u else err("Not logged in.", 401)

    @app.post("/api/auth/authority/request")
    def authority_request():
        if not thr.hit(("authreq", ip()), 10, 3600):
            return err("Too many requests from this connection. Please try again later.", 429)
        b = body_json()
        if b is None:
            return err("Send a JSON object.", 400)
        try:
            acc.request_authority(b)
        except ValueError as e:
            return err(str(e), 400)
        except Conflict as e:
            return err(str(e), 409)
        return jsonify({"status": "pending"}), 201

    # ------------------------------------------------------------------ family
    @app.post("/api/missing")
    @guarded(need_family)
    def post_missing():
        b = body_json()
        if b is None:
            return err("Send a JSON object.", 400)
        u = current_user()
        member_id = str(b.get("member_id") or "").strip() or None
        try:
            if member_id:
                acc.check_member(u["email"], member_id)
            res = eng.add_missing(b)
        except KeyError as e:
            return err(str(e.args[0]), 400)
        except ValueError as e:
            return err(str(e), 400)
        acc.link_report(u["email"], res["id"], member_id)
        return jsonify(res), 201

    @app.get("/api/family/members")
    @guarded(need_family)
    def members_list():
        return jsonify(acc.list_members(current_user()["email"], eng.status))

    @app.post("/api/family/members")
    @guarded(need_family)
    def members_add():
        b = body_json()
        if b is None:
            return err("Send a JSON object.", 400)
        try:
            return jsonify({"id": acc.add_member(current_user()["email"], b)}), 201
        except ValueError as e:
            return err(str(e), 400)

    @app.delete("/api/family/members/<mid>")
    @guarded(need_family)
    def members_delete(mid):
        try:
            acc.delete_member(current_user()["email"], mid)
        except KeyError as e:
            return err(str(e.args[0]), 404)
        return jsonify({"ok": True})

    @app.get("/api/family/reports")
    @guarded(need_family)
    def family_reports():
        out = []
        for r in acc.family_reports(current_user()["email"]):
            i = eng._index(r["id"])
            if i is None:
                continue
            row = eng.mdf.iloc[i]
            out.append({"id": r["id"], "status": eng.status(r["id"]), "member_name": r["member_name"],
                        "last_seen_place": row["last_seen_place"], "last_seen_time": row["last_seen_time"]})
        return jsonify(out)

    # ------------------------------------------------------------------ authority (staff login: role authority or admin)
    @app.get("/api/missing")
    @guarded(need_authority)
    def list_missing():
        return jsonify(eng.list_missing())

    @app.post("/api/found")
    @guarded(need_authority)
    def post_found():
        b = body_json()
        if b is None:
            return err("Send a JSON object.", 400)
        try:
            return jsonify(eng.add_found(b, source="authority")), 201
        except ValueError as e:
            return err(str(e), 400)

    @app.get("/api/matches/<mid>")
    @guarded(need_authority)
    def matches(mid):
        m = eng.matches(mid)
        return jsonify(m) if m else err("No report with that ID.", 404)

    @app.post("/api/matches/<mid>/decision")
    @guarded(need_authority)
    def decision(mid):
        b = body_json() or {}
        try:
            return jsonify(eng.decide(mid, str(b.get("found_id", "")), str(b.get("decision", ""))))
        except KeyError as e:
            return err(str(e.args[0]), 404)
        except PermissionError as e:
            return err(str(e), 409)
        except ValueError as e:
            return err(str(e), 400)

    @app.post("/api/rescan")
    @guarded(need_authority)
    def rescan():
        return jsonify(eng.rescan())

    # ------------------------------------------------------------------ admin
    @app.get("/api/admin/requests")
    @guarded(need_admin)
    def admin_requests():
        return jsonify(acc.pending_requests())

    @app.post("/api/admin/requests/<email>/approve")
    @guarded(need_admin)
    def admin_approve(email):
        try:
            acc.approve(email)
        except KeyError as e:
            return err(str(e.args[0]), 404)
        return jsonify({"ok": True})

    @app.post("/api/admin/requests/<email>/reject")
    @guarded(need_admin)
    def admin_reject(email):
        try:
            acc.reject(email)
        except KeyError as e:
            return err(str(e.args[0]), 404)
        return jsonify({"ok": True})

    @app.get("/api/admin/authorities")
    @guarded(need_admin)
    def admin_authorities():
        return jsonify(acc.authorities())

    @app.post("/api/admin/authorities")
    @guarded(need_admin)
    def admin_create_authority():
        b = body_json()
        if b is None:
            return err("Send a JSON object.", 400)
        try:
            return jsonify(acc.create_authority(b.get("name"), b.get("email"), b.get("password"))), 201
        except ValueError as e:
            return err(str(e), 400)
        except Conflict as e:
            return err(str(e), 409)

    @app.delete("/api/admin/authorities/<email>")
    @guarded(need_admin)
    def admin_delete_authority(email):
        try:
            acc.delete_authority(email)
        except KeyError as e:
            return err(str(e.args[0]), 404)
        except Forbidden as e:
            return err(str(e), 403)
        return jsonify({"ok": True})

    # ------------------------------------------------------------------ front end (whole folder, subfolders included)
    def serve(p):
        front = find_frontend()
        if not front:
            return (FALLBACK_PAGE, 200) if p in ("", "index.html") else ("Not found", 404)
        full = safe_join(front, p)
        if full and os.path.isdir(full):
            p, full = (p.rstrip("/") + "/index.html").lstrip("/"), os.path.join(full, "index.html")
        if full and os.path.isfile(full):
            return send_from_directory(front, p)
        return ("Not found", 404)

    @app.get("/")
    def index():
        return serve("")

    @app.get("/<path:p>")
    def static_files(p):
        if p.startswith("api/"):
            return err("Not found.", 404)
        return serve(p)

    app.engine, app.accounts = eng, acc
    return app


if __name__ == "__main__":
    app = create_app()
    if not any(u["role"] == "admin" for u in app.accounts.d["users"].values()):
        print("[app] no admin account yet. Run:  python create_admin.py you@example.com 'a-long-password'")
    print(f"[app] front end: {find_frontend() or 'none found (a placeholder page is shown)'}")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), threaded=True)
