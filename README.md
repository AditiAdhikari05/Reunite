# DisasterBridge-AI

A prototype for the IBM Z Datathon that helps reunite families after a disaster.

- **Families** report people who are missing.
- **Authorities** (rescue, shelter, hospital and police staff) record people they have found.
- A **matching engine** suggests which missing and found records may be the same person, with a score and the reasons for it.
- **A human must confirm every match.** Families only ever see a status, never details of found people.

The app is designed to run on **IBM LinuxONE** (Linux on IBM Z, `s390x`). The Flask API and the matching engine run on the server, so sensitive data stays there.

> Demo using synthetic data only. Do not enter real personal information.

## Current status

| Part | Status |
|---|---|
| Frontend (`frontend/`) | Done. Runs in **mock mode** with synthetic data |
| Flask backend | In progress (backend teammate) |
| Matching engine | In progress (AI teammate). The frontend shows mock scores for now |
| LinuxONE deployment | Not yet deployed |
| Benchmark numbers | **Illustrative placeholders, not measured results** |

## Run the frontend locally

You only need Python 3. There is no Node, no npm and no build step.

```bash
cd frontend
python3 -m http.server 5500
```

Then open <http://localhost:5500/>.

Use the local server instead of double-clicking the HTML files. Pages opened as `file://` cannot share demo data between the family and authority portals.

### Demo logins (mock mode only)

| Portal | Email | Password |
|---|---|---|
| Family | `family@disasterbridge.demo` | `demo-family-2026` |
| Authority (admin) | `admin@disasterbridge.demo` | `demo-admin-2026` |
| Authority (officer) | `officer@disasterbridge.demo` | `demo-officer-2026` |

These accounts are fake and exist only inside `app.js` for the demo. The real backend must keep its own accounts, with hashed passwords.

### Try the full flow

1. Log in to the **family portal** and report someone missing. Note the report number, for example `M13`.
2. Log in to the **authority portal** in another tab. The new report appears in the table.
3. Click a report to see suggested matches. Confirm one.
4. Back in the family portal, the report now shows **Reunited**.
5. In the authority portal, use **Reset demo data** to start again.

In mock mode, data is saved in your browser's local storage, so it only exists in that browser. Logins last for the current tab only.

## Folder structure

```
frontend/
  index.html               Welcome page: choose family or authority
  platform.html            "How this runs on IBM LinuxONE" and benchmark bars
  app.js                   Shared code: USE_MOCK switch, API helper, mock backend, form helpers
  style.css                Shared styles (both portals)
  family/                  Family portal
    login.html  signup.html  index.html (dashboard)  family.js
  authority/               Authority portal
    login.html  request-access.html  index.html (dashboard)  authority.js
  authority.html           Redirects to authority/login.html (old link)
```

### Pages

**Family portal (`family/`)**
- Sign up (name, email, phone, password, consent) and log in.
- **My family**: save details of family members in advance.
- **Report a missing person**: choose a saved family member to fill in the form, or describe someone else.
- **My reports**: each report shows only one of *Searching*, *Possible match under review* or *Reunited*.

**Authority portal (`authority/`)**
- Log in only. There is no open sign-up. New staff use **Request access**, and the administrator approves or declines each request.
- A table of missing-person reports.
- **Add a found person**.
- **Match review**: ranked candidates with a score bar, ✓/✗ reasons, a side-by-side comparison, and Confirm and Reject buttons.
- A permanent banner: *Scores are suggestions. A human must verify every match.*
- **Admin only**: approve access requests, add authority accounts directly, and remove authority accounts.

## Mock mode vs live backend

The first line of `frontend/app.js` is:

```js
const USE_MOCK = true;
```

- `true`: every API call is answered by the synthetic mock inside `app.js`. No server is needed.
- `false`: calls go to the real Flask API with `fetch("/api/...")`, using relative URLs.

Switch it to `false` only once the Flask endpoints below are working. Then run the full flow again end to end.

## API contract

All request and response bodies are JSON. Errors return `{"error": "message"}` with a 4xx status. Dates are ISO strings like `"2026-10-17T14:30"`.

Login uses a **server session cookie**. The frontend never stores passwords or tokens. The backend must check the user's role on every restricted route, not just hide things in the UI.

### Original routes

| Method | Route | Who | Purpose |
|---|---|---|---|
| POST | `/api/missing` | family | Create a missing report. Can include `member_id` |
| GET | `/api/status/<id>` | anyone | Public status only: `{"id", "status"}` |
| POST | `/api/found` | authority | Create a found record |
| GET | `/api/missing` | authority | List all missing reports (full records, with `id`, `status`, `summary`) |
| GET | `/api/matches/<missing_id>` | authority | Ranked candidates |
| POST | `/api/matches/<missing_id>/decision` | authority | `{"found_id": "F7", "decision": "confirm" \| "reject"}` |
| GET | `/api/benchmark` | anyone | Accelerator on and off timings |

The `status` value must be exactly `searching`, `under_review` or `reunited`.

### Account routes

| Method | Route | Who | Purpose |
|---|---|---|---|
| POST | `/api/auth/signup` | anyone | `{name, email, phone, password}` creates a **family** account and logs in. Returns `{user}` |
| POST | `/api/auth/login` | anyone | `{email, password, role: "family" \| "authority"}`. Returns `{user}`. A pending authority gets 403 |
| POST | `/api/auth/logout` | logged in | Ends the session |
| GET | `/api/auth/me` | logged in | `{user: {email, name, role}}`, or 401 |
| POST | `/api/auth/authority/request` | anyone | `{name, email, agency, position, staff_id, reason, password}` creates a **pending** request |

### Family routes

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/family/members` | This family's members, each with `report_id` and `status` if reported |
| POST | `/api/family/members` | `{name, relationship, age, gender, height_cm, hair, marks, notes}` |
| DELETE | `/api/family/members/<id>` | Remove a member |
| GET | `/api/family/reports` | `[{id, status, member_name, last_seen_place, last_seen_time}]` |

### Admin routes (role `admin` only)

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/admin/requests` | Pending access requests |
| POST | `/api/admin/requests/<email>/approve` | Turn the request into an authority account |
| POST | `/api/admin/requests/<email>/reject` | Delete the request |
| GET | `/api/admin/authorities` | Authority and admin accounts |
| POST | `/api/admin/authorities` | `{name, email, password}` adds an authority directly |
| DELETE | `/api/admin/authorities/<email>` | Remove an authority account |

Roles are `family`, `authority`, `admin` and `pending`. An admin can do everything an authority can.

### Example bodies

Missing report (`POST /api/missing`):

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

Found records use `found_place`, `found_time` and `current_location` instead of the "last seen" fields, and have no `contact` field.

Candidates (`GET /api/matches/M12`):

```json
{
  "missing_id": "M12",
  "candidates": [{
    "found_id": "F7", "score": 87,
    "reasons": [
      {"label": "Age ranges overlap", "matched": true},
      {"label": "Clothing differs (red jacket vs blue coat)", "matched": false}
    ],
    "found": {"age_min": 30, "age_max": 36, "gender": "female", "clothing": "blue coat",
              "found_place": "Bridge Road", "found_time": "2026-10-17T00:10",
              "current_location": "City Shelter 2"}
  }]
}
```

## Notes for the backend

- Serve the whole `frontend/` folder, including the `family/` and `authority/` subfolders, as static files from Flask.
- Use a secure, httpOnly session cookie, and store passwords hashed (for example with `werkzeug.security`).
- Enforce roles on the server for every family, authority and admin route.
- Never return found-person details or reviewer data from family routes.
- Create the real admin account on the server. Never put real credentials in the frontend or in Git.
- Keep Flask's debug server for local development only. Use a proper WSGI server on LinuxONE.

## Delivery

Zip the `frontend/` folder and upload it to the team's `shared` folder with the Jupyter file browser. No server keys are needed.

## Not done yet

- Real Flask backend and database
- Real matching engine (the mock uses a simple stand-in scorer)
- Measured LinuxONE benchmark numbers
- Password reset ("Forgot password") and email notifications
