# Reunite

A prototype for the IBM Z Datathon that helps reunite families after a disaster.

- **Families** report people who are missing.
- **Authorities** (rescue, shelter, hospital and police staff) record people they have found.
- **Anyone** can report a person they found, without an account.
- A **matching engine** ranks which missing and found records may be the same person, with a score and the reasons for it.
- **A human must confirm every match.** Families only ever see a status, never match details or scores.

The app runs on **IBM LinuxONE** (Linux on IBM Z, `s390x`). The Flask API and the matching engine run on the server, so sensitive data stays there.

> Demo using synthetic data only. Do not enter real personal information.

## Current status

| Part | Owner | Status |
|---|---|---|
| Frontend (`frontend/`) | Aditi | Done. Runs in **mock mode** with synthetic data |
| Flask backend | Swastik | In progress. Planned at `http://148.100.76.31:5000` (not reachable yet) |
| Account routes (sign-up, login, admin) | Swastik | **Needed.** Not in the original backend contract |
| Matching engine | Team | In progress. The frontend shows mock scores for now |
| Benchmark numbers | Team | **Placeholders, not measured results** |

## Run the frontend locally

You only need Python 3. There is no Node, no npm and no build step.

```bash
cd frontend
python3 -m http.server 5500
```

Then open <http://localhost:5500/>. Use the local server instead of double-clicking the HTML files, because pages opened as `file://` cannot share demo data.

### Demo logins (mock mode only)

| Portal | Email | Password | PIN |
|---|---|---|---|
| Family | `family@reunite.demo` | `demo-family-2026` | – |
| Authority (admin) | `admin@reunite.demo` | `demo-admin-2026` | any number in mock mode |
| Authority (officer) | `officer@reunite.demo` | `demo-officer-2026` | any number in mock mode |

These accounts are fake and exist only inside `app.js`. The **real PIN** comes from Swastik. It is typed in at login and **never stored in the code**.

## Live demo script (for the judges)

Add `?demo=1` to a page address to show the hidden **Demo helper** panel. It lists only the cases marked `good_for_live_demo` from `GET /api/demo-cases`.

1. Family portal: open `family/index.html?demo=1`, click **Fill missing report**, then **Send report**. Note the number, for example `M13`.
2. Open `status.html?id=M13`. It shows **Searching**.
3. Authority portal: open `authority/index.html?demo=1`, click **Fill found record** for the same case, then **Save found person**.
4. The status page flips to **Possible match under review**. It refreshes itself every 15 seconds. The report is flagged ⚑ in the authority table.
5. Open the report, check the reasons, and **Confirm**. The status becomes **Reunited**. **Undo** reverses it.

In mock mode, **Reset demo data** (authority dashboard) starts again from scratch.

## Folder structure

```
frontend/
  index.html               Welcome page: family / authority / "Report a person found"
  status.html              Public status check by report number (no login)
  report-found.html        Public found-person report (no login)
  platform.html            "How it works": LinuxONE explanation and benchmark results
  app.js                   Shared code: USE_MOCK switch, API helper, mock backend, public pages
  style.css                Shared styles
  family/                  Family portal: login, signup, dashboard (family.js)
  authority/               Authority portal: login (email, password, PIN), request access, dashboard (authority.js)
  authority.html           Redirects to authority/login.html
```

## Mock mode vs live backend

The first line of `frontend/app.js` is:

```js
const USE_MOCK = true;
```

Keep it `true` until Swastik confirms the server is up. Then set it to `false`, upload the folder, and run the live demo script end to end. Send Swastik any response that does not match the contract below, with the request and response pasted in.

## API contract

All bodies are JSON. Errors return `{"error": "message"}` with a 4xx status. Dates are ISO strings like `"2026-10-17T14:30"`. All URLs are relative (`fetch("/api/...")`).

Authority routes send **`X-Auth-Pin: <pin>`**. Account routes use a **session cookie**.

### Core routes (from Swastik's brief)

| Method | Route | Who | Request / response |
|---|---|---|---|
| GET | `/api/places` | anyone | List of place names (strings, or objects with `name`). Feeds the place autocomplete |
| POST | `/api/missing` | family | Missing report (below). Returns `{id, status}` |
| GET | `/api/status/<id>` | anyone | `{id, status, authority_contact}`. `status` is `searching`, `possible_match` or `reunited`. **No match details** |
| POST | `/api/found` | authority + PIN | Found record. Returns `{id}` |
| GET | `/api/missing` | authority + PIN | All reports with `id`, `status`, `summary` and **`flagged`** (true if the engine flagged it) |
| GET | `/api/matches/<id>` | authority + PIN | `{missing_id, missing?, candidates: [...]}`. The frontend shows the top 10 |
| POST | `/api/matches/<id>/decision` | authority + PIN | `{found_id, decision: "confirm" \| "reject" \| "undo"}`. **409** if that found person is already claimed by another report |
| GET | `/api/demo-cases` | anyone | `[{id, title, good_for_live_demo, missing: {...}, found: {...}}]` |
| GET | `/api/benchmark` | anyone | See below |

Each candidate: `{found_id, score (0–100), reasons: [{label, matched}], found: {...}, decision: "confirmed" | "rejected" | null, claimed_by: "M12" | null}`.

### Routes added by the frontend (Swastik to build)

| Method | Route | Who | Purpose |
|---|---|---|---|
| POST | `/api/public/found` | anyone | Found-person report from the public. Adds `reporter_name`, `reporter_phone`. Stored with `source: "public"` |
| POST | `/api/auth/signup` | anyone | `{name, email, phone, password}` creates a **family** account and logs in |
| POST | `/api/auth/login` | anyone | `{email, password, role: "family" \| "authority"}`. A pending authority gets 403 |
| POST | `/api/auth/logout` | logged in | Ends the session |
| GET | `/api/auth/me` | logged in | `{user: {email, name, role}}` or 401 |
| POST | `/api/auth/authority/request` | anyone | `{name, email, agency, position, staff_id, reason, password}` creates a pending request |
| GET / POST | `/api/family/members` | family | List or add family members |
| DELETE | `/api/family/members/<id>` | family | Remove a member |
| GET | `/api/family/reports` | family | `[{id, status, member_name, last_seen_place, last_seen_time}]` |
| GET | `/api/admin/requests` | admin | Pending access requests |
| POST | `/api/admin/requests/<email>/approve` or `/reject` | admin | Approve or decline |
| GET / POST | `/api/admin/authorities` | admin | List, or add `{name, email, password}` |
| DELETE | `/api/admin/authorities/<email>` | admin | Remove access |

### Missing report body

```json
{
  "member_id": "P1",
  "age_min": 28, "age_max": 34, "gender": "female", "height_cm": 165,
  "hair": "black, shoulder length", "clothing": "red jacket, jeans",
  "marks": "scar above left eyebrow",
  "last_seen_place": "Riverside Market", "last_seen_time": "2026-10-16T18:00",
  "description": "Last seen heading towards the bridge.",
  "contact": "555-0100"
}
```

Found records use `found_place`, `found_time` and `current_location` instead of the "last seen" fields, and have no `contact`.

### Benchmark format the page expects

```json
{
  "note": "free text, shown as-is",
  "accuracy": { "cases": 200, "engine": {"top1": 0.78, "top5": 0.94}, "keyword": {"top1": 0.41, "top5": 0.66} },
  "speed": { "pairs": 40000, "full_rescan_seconds": 1.9 },
  "chip": { "on": {"seconds": 1.9}, "off": {"seconds": 2.0}, "note": "free text, shown as-is" }
}
```

Fractions (0–1) and percentages both work. Any section that is missing shows "not available yet". The page also shows the **full raw output**, so nothing is hidden or reworded, including chip results that didn't help.

## Not done yet

- Real backend, including the account routes above
- Real matching engine and measured benchmark numbers
- Password reset and email notifications
