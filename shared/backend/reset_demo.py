"""
reset_demo.py - wipe everything that was filed during testing, so the demo starts from a clean slate.

  python3 stop_app.py                       # stop the app first (the app keeps its data in memory)
  python3 reset_demo.py                     # clears: reports and found people added after start-up, match decisions,
                                            #         family members and the links between families and reports
  python3 reset_demo.py --accounts          # also removes all family, authority and pending accounts (admin accounts stay)
  PRELOAD=none nohup python3 app.py > app.log 2>&1 &     # start with NO sample reports or found people at all

A backup of the old files is kept in state/backup_<time>/ so nothing is lost by accident.
Settings are the same as app.py: STATE_PATH, ACCOUNTS_PATH, STATE_KEY.
"""
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from store import read_json, state_key, write_json  # noqa: E402

STATE_PATH = os.environ.get("STATE_PATH", os.path.join(HERE, "state", "state.json"))
ACCOUNTS_PATH = os.environ.get("ACCOUNTS_PATH", os.path.join(os.path.dirname(os.path.abspath(STATE_PATH)), "users.json"))
key = state_key()
wipe_accounts = "--accounts" in sys.argv

backup = os.path.join(os.path.dirname(os.path.abspath(STATE_PATH)), time.strftime("backup_%Y%m%d_%H%M%S"))
os.makedirs(backup, exist_ok=True)
for p in (STATE_PATH, ACCOUNTS_PATH):
    if os.path.exists(p):
        shutil.copy2(p, backup)
print("backup saved in", backup)

if os.path.exists(STATE_PATH):
    os.remove(STATE_PATH)
    print("cleared: reports, found people, decisions")
else:
    print("no saved reports or decisions (already empty)")

if os.path.exists(ACCOUNTS_PATH):
    d = read_json(ACCOUNTS_PATH, key)
    d["members"], d["reports"], d["next_member"] = {}, {}, 1
    kept = {e: u for e, u in d.get("users", {}).items() if u.get("role") == "admin"}
    if wipe_accounts:
        print(f"removed {len(d.get('users', {})) - len(kept)} family / authority / pending accounts; kept {len(kept)} admin account(s)")
        d["users"] = kept
    else:
        print("kept all accounts (use --accounts to remove family and authority accounts too)")
    write_json(ACCOUNTS_PATH, d, key)
    print("cleared: family members and report links")
else:
    print("no accounts file yet")
print("\nNext: start the app. Add PRELOAD=none in front of the command to start with no sample data at all.")
