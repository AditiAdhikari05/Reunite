"""
create_admin.py - creates (or resets) the administrator account.   Run:  python3 create_admin.py you@example.com 'a-long-password'
The password is stored only as a salted hash. Do not put it in the front end, in git, or in screenshots.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from accounts import Accounts  # noqa: E402
from store import state_key  # noqa: E402

if len(sys.argv) < 3:
    sys.exit("Usage: python3 create_admin.py EMAIL PASSWORD [NAME]")
state = os.environ.get("STATE_PATH", os.path.join(HERE, "state", "state.json"))
path = os.environ.get("ACCOUNTS_PATH", os.path.join(os.path.dirname(os.path.abspath(state)), "users.json"))
try:
    Accounts(path, state_key()).ensure_admin(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "Administrator")
except ValueError as e:
    sys.exit(f"Could not create the admin: {e}")
print(f"Admin account ready for {sys.argv[1].lower()}. Restart the app if it is already running.")
