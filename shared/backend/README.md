# Reunite AI backend

Matches missing-person reports to found-person records. A human reviews every match. All data is synthetic.

## Folder layout (inside the LinuxONE Jupyter container)

    shared/
      backend/   <- this folder
      data/      <- missing.csv, found.csv, places.csv, truth.csv
      frontend/  <- Aditi's HTML/CSS/JS (index.html, family/, authority/ ...). Picked up without a restart.

## First-time setup (in a Jupyter Terminal, use python3)

    cd ~/shared/backend
    pip install flask --break-system-packages
    python3 train.py --data ../data --out models        # about 30 s; prints the held-out results table
    python3 selftest.py                                  # must end with "0 failed"
    python3 create_admin.py you@example.com 'a-long-password'     # the one real admin account (stored hashed)
    nohup python3 app.py > app.log 2>&1 &

Open http://<server-ip>:5000 . Health check: /api/health . Stop the app: `python3 stop_app.py` (the container has no pkill).
Look at the log: `tail -f app.log` .

## Who can do what

- **Public:** /api/places, /api/status/<id>, /api/benchmark, /api/demo-cases, POST /api/public/found, sign up, log in.
- **Family** (login): POST /api/missing, /api/family/members, /api/family/reports.
- **Authority** (staff login with email + password; there is no PIN any more): GET /api/missing, POST /api/found,
  GET /api/matches/<id>, POST /api/matches/<id>/decision, POST /api/rescan.
- **Admin** (login): /api/admin/requests (+ /approve, /reject), /api/admin/authorities. An admin can also act as an authority.
- Authority sign-up goes through POST /api/auth/authority/request and stays "pending" until an admin approves it.

Errors are JSON: {"error": "plain-language message"}. Families only ever see status + the authority contact line.

## Settings (environment variables, all optional)

    ADMIN_EMAIL, ADMIN_PASSWORD creates/updates the admin at start-up (alternative to create_admin.py)
    SECRET_KEY                  signs login cookies; default: random key saved in state/secret.key
    COOKIE_SECURE=1             when served over HTTPS
    AUTHORITY_CONTACT           contact line shown on the family status page
    FRONTEND_DIR, DATA_DIR, MODEL_DIR, STATE_PATH, ACCOUNTS_PATH, PORT
    SCORER_BACKEND              auto | numpy | tf
    REUNITE_GRANITE=1           also read descriptions with Granite 350M (needs torch + transformers; default: regex only)
    GRANITE_MODEL, DEVICE       model name / force a device (nnpa or cpu) for Granite
    STATE_KEY                   passphrase: encrypts saved data with AES-256-GCM. Needs the 'cryptography' package, which has no
                                ready-made build for s390x (pip cannot install it in the container) - leave unset there.

Saved data lives in backend/state/ (state.json = reports and decisions, users.json = accounts). Delete that folder to reset.

## Starting the demo from a clean slate

    python3 stop_app.py                                    # the app keeps data in memory, so stop it first
    python3 reset_demo.py --accounts                       # wipes testing leftovers; keeps a backup in state/backup_<time>/
    PRELOAD=none nohup python3 app.py > app.log 2>&1 &     # start with NO sample reports or found people

`reset_demo.py` clears reports and found people filed after start-up, match decisions, family members and report links.
`--accounts` also removes family / authority / pending accounts (admin accounts stay). Without `PRELOAD=none` the app still
loads the 400 sample reports and 600 sample found people, which is what you want if you prefer the demo report to be ranked
against a realistic pool. Check with /api/health: `"preload": "none", "reports": 0, "found_people": 0`.
With an empty start, ids begin at M1 and F1, and a report with nobody to compare against simply has no candidates yet.

## End-to-end proof (for the demo and slides)

    python3 e2e_check.py      # accuracy on held-out reports + a live walk-through on a private copy of the app
                              # writes results/e2e_report.md and results/e2e_results.json

## Chip benchmarks (optional)

    python3 bench_scorer.py                        # our small matcher: numpy vs accelerator off/on -> models/benchmark_scorer.json
    python3 chip_models_bench.py                   # MiniLM + Granite on the accelerator vs CPU, repeated, with an output comparison
                                                   # -> models/chip_models.json (needs torch + transformers + the two models, a few minutes)

Both feed /api/benchmark under "chip". Restart is not needed; the file is read on each request.

## Reading the description (free text)

If a report is filed with empty hair / clothing / marks boxes, `extract.py` reads them from the description and records
which boxes it filled in `auto_filled` (typed boxes are never overwritten). Regex is always on. Granite 350M is optional:

    REUNITE_GRANITE=1 nohup python3 app.py > app.log 2>&1 &     # loads in the background; falls back to regex if anything fails

Every Granite answer passes a grounding check (details that are not in the text are dropped). Check it with:

    python3 extract_check.py                       # extraction quality + matching with blank boxes (set REUNITE_GRANITE=1 for Granite)
    python3 robustness_check.py ../shared/data_hard   # the trained matcher on Aneeza's harder dataset (new wording, more typos)

## Honest notes

- The deployed scorer is logistic regression over 33 pair features; neural variants were tested and scored lower.
- Scores are ranking scores, not probabilities. Synthetic data only.
- If you change the CSVs, re-run train.py, then restart the app.
