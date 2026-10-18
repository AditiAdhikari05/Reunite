"""
accounts.py - user accounts for the web app: families, authority staff, admins, plus each family's members and reports.

Roles: family, authority, admin, pending (an authority who asked for access and is waiting for an admin).
Passwords are stored only as salted hashes. Data is saved in one JSON file (encrypted if STATE_KEY is set).
"""
import contextlib
import os
import re
import threading
import time

from werkzeug.security import check_password_hash, generate_password_hash

from store import read_json, write_json

HASH_METHOD = "pbkdf2:sha256:600000"
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]+$")
_DUMMY_HASH = generate_password_hash("not-a-real-password", method=HASH_METHOD)   # so unknown emails take the same time


class Conflict(Exception):          # -> 409
    pass


class Forbidden(Exception):         # -> 403
    pass


class AuthFailed(Exception):        # -> 401
    pass


def _text(v, n=200):
    return re.sub(r"[\x00-\x1f\x7f]", " ", "" if v is None else str(v)).strip()[:n]


def norm_email(e):
    e = _text(e, 120).lower()
    if not EMAIL_RE.match(e):
        raise ValueError("Please enter a valid email address.")
    return e


def check_password(p):
    if not isinstance(p, str) or len(p) < 8:
        raise ValueError("The password must be at least 8 characters long.")
    if len(p) > 200:
        raise ValueError("That password is too long.")
    return p


def public_user(u):
    return {"email": u["email"], "name": u["name"], "role": u["role"]}


class Accounts:
    def __init__(self, path, key=None):
        self.path, self.key = path, key
        self.lock = threading.RLock()
        self.d = {"users": {}, "members": {}, "reports": {}, "next_member": 1}
        self._mtime = None
        self._reload()

    def _reload(self):
        if os.path.exists(self.path):
            self.d.update(read_json(self.path, self.key))
            self._mtime = os.path.getmtime(self.path)

    @contextlib.contextmanager
    def _sync(self):
        """Take the lock and pick up changes made by another process (for example create_admin.py while the app runs)."""
        with self.lock:
            if os.path.exists(self.path) and os.path.getmtime(self.path) != self._mtime:
                self._reload()
            yield

    def _save(self):
        write_json(self.path, self.d, self.key)
        self._mtime = os.path.getmtime(self.path)

    # ------------------------------------------------------------------ sign up / log in
    def _new_user(self, email, name, role, password, **extra):
        if email in self.d["users"]:
            raise Conflict("An account with that email already exists.")
        u = {"email": email, "name": name, "role": role, "pw": generate_password_hash(password, method=HASH_METHOD),
             "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"), **extra}
        self.d["users"][email] = u
        self._save()
        return u

    def signup_family(self, name, email, phone, password):
        name = _text(name, 100)
        if not name:
            raise ValueError("Please enter your name.")
        email, password = norm_email(email), check_password(password)
        with self._sync():
            return public_user(self._new_user(email, name, "family", password, phone=_text(phone, 40)))

    def request_authority(self, body):
        f = {k: _text(body.get(k), 300 if k == "reason" else 120) for k in ("name", "agency", "position", "staff_id", "reason")}
        for k, label in (("name", "your name"), ("agency", "your agency"), ("position", "your position"),
                         ("staff_id", "your staff ID"), ("reason", "a reason for the request")):
            if not f[k]:
                raise ValueError(f"Please enter {label}.")
        email, password = norm_email(body.get("email")), check_password(body.get("password"))
        with self._sync():
            self._new_user(email, f["name"], "pending", password, agency=f["agency"], position=f["position"],
                           staff_id=f["staff_id"], reason=f["reason"], requested_at=time.strftime("%Y-%m-%dT%H:%M:%S"))

    def authenticate(self, email, password, side):
        """side is 'family', 'authority' or 'admin'. Wrong password OR wrong side gives the same AuthFailed."""
        try:
            email = norm_email(email)
        except ValueError:
            email = ""
        with self._sync():
            u = self.d["users"].get(email)
        ok = check_password_hash(u["pw"] if u else _DUMMY_HASH, password if isinstance(password, str) else "")
        if not (u and ok):
            raise AuthFailed("Wrong email or password.")
        if u["role"] == "pending":
            if side == "authority":
                raise Forbidden("Your request for authority access is still waiting for approval by an administrator.")
            raise AuthFailed("Wrong email or password.")
        allowed = {"family": ("family",), "authority": ("authority", "admin"), "admin": ("admin",)}.get(side, ())
        if u["role"] not in allowed:
            raise AuthFailed("Wrong email or password." if side == "family" else
                             "This account cannot sign in here. Use the sign-in page for your account type.")
        return public_user(u)

    def get(self, email):
        with self._sync():
            u = self.d["users"].get(email)
            return public_user(u) if u else None

    def ensure_admin(self, email, password, name="Administrator"):
        email, password = norm_email(email), check_password(password)
        with self._sync():
            u = self.d["users"].get(email)
            if u:
                u.update(role="admin", pw=generate_password_hash(password, method=HASH_METHOD))
                self._save()
            else:
                self._new_user(email, _text(name, 100) or "Administrator", "admin", password)

    # ------------------------------------------------------------------ family members and reports
    def check_member(self, owner, member_id):
        with self._sync():
            m = self.d["members"].get(member_id)
            if not m or m["owner"] != owner:
                raise KeyError("That family member is not on your account.")

    def add_member(self, owner, body):
        if not isinstance(body, dict):
            raise ValueError("Send a JSON object.")
        name = _text(body.get("name"), 100)
        if not name:
            raise ValueError("Please enter the person's name.")
        try:
            age = body.get("age")
            age = int(float(age)) if age not in (None, "") else None
            if age is not None and not 0 <= age <= 120:
                raise ValueError
        except (TypeError, ValueError):
            raise ValueError("Age must be a number between 0 and 120.")
        try:
            h = body.get("height_cm")
            h = float(h) if h not in (None, "") else None
            if h is not None and not 30 <= h <= 250:
                raise ValueError
        except (TypeError, ValueError):
            raise ValueError("Height must be a number of centimetres between 30 and 250.")
        g = _text(body.get("gender"), 20).lower()
        with self._sync():
            mid = f"P{self.d['next_member']}"
            self.d["next_member"] += 1
            self.d["members"][mid] = {"id": mid, "owner": owner, "name": name, "relationship": _text(body.get("relationship"), 60),
                                      "age": age, "gender": g if g in ("female", "male", "other", "unknown") else "unknown",
                                      "height_cm": h, "hair": _text(body.get("hair"), 120), "marks": _text(body.get("marks"), 200),
                                      "notes": _text(body.get("notes"), 500), "report_id": None}
            self._save()
            return mid

    def list_members(self, owner, status_of):
        with self._sync():
            out = []
            for m in self.d["members"].values():
                if m["owner"] == owner:
                    row = {k: v for k, v in m.items() if k != "owner"}
                    row["status"] = status_of(m["report_id"]) if m["report_id"] else None
                    out.append(row)
            return out

    def delete_member(self, owner, member_id):
        with self._sync():
            self.check_member(owner, member_id)
            del self.d["members"][member_id]
            for r in self.d["reports"].values():
                if r.get("member_id") == member_id:
                    r["member_id"] = None
            self._save()

    def link_report(self, owner, report_id, member_id):
        with self._sync():
            self.d["reports"][report_id] = {"owner": owner, "member_id": member_id or None}
            if member_id:
                self.d["members"][member_id]["report_id"] = report_id
            self._save()

    def family_reports(self, owner):
        with self._sync():
            out = []
            for rid, r in self.d["reports"].items():
                if r["owner"] == owner:
                    m = self.d["members"].get(r["member_id"]) if r.get("member_id") else None
                    out.append({"id": rid, "member_name": m["name"] if m else f"Report {rid}"})
            return out

    # ------------------------------------------------------------------ admin
    def pending_requests(self):
        with self._sync():
            return [{k: u.get(k) for k in ("email", "name", "agency", "position", "staff_id", "reason", "requested_at")}
                    for u in self.d["users"].values() if u["role"] == "pending"]

    def approve(self, email):
        with self._sync():
            u = self.d["users"].get(email.lower())
            if not u or u["role"] != "pending":
                raise KeyError("No pending request for that email.")
            u["role"] = "authority"
            self._save()

    def reject(self, email):
        with self._sync():
            u = self.d["users"].get(email.lower())
            if not u or u["role"] != "pending":
                raise KeyError("No pending request for that email.")
            del self.d["users"][email.lower()]
            self._save()

    def authorities(self):
        with self._sync():
            return [public_user(u) for u in self.d["users"].values() if u["role"] in ("authority", "admin")]

    def create_authority(self, name, email, password):
        name = _text(name, 100)
        if not name:
            raise ValueError("Please enter a name.")
        email, password = norm_email(email), check_password(password)
        with self._sync():
            return public_user(self._new_user(email, name, "authority", password))

    def delete_authority(self, email):
        with self._sync():
            u = self.d["users"].get(email.lower())
            if not u or u["role"] not in ("authority", "admin"):
                raise KeyError("No authority account with that email.")
            if u["role"] == "admin":
                raise Forbidden("Administrator accounts cannot be removed here.")
            del self.d["users"][email.lower()]
            self._save()
