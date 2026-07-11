"""
Shared config for the Roll Roll Roll scripts.
Only ever operates as YOUR OWN player. Do not point this at teammates'
or other players' userIds without their consent.

Player id resolution order:
  1. --user-id CLI flag (any script)
  2. ROLL_USER_ID environment variable
  3. error - no hardcoded default, everyone must supply their own id
"""

import os
import sys

BASE_URL = "https://roll.createwithclint.com/api"
WS_URL = "wss://roll.createwithclint.com"


def _resolve_user_id():
    if "--user-id" in sys.argv:
        idx = sys.argv.index("--user-id")
        if idx + 1 < len(sys.argv):
            return sys.argv[idx + 1]
    for arg in sys.argv:
        if arg.startswith("--user-id="):
            return arg.split("=", 1)[1]

    return os.environ.get("ROLL_USER_ID")


def require_user_id():
    """Call this from scripts that need an authenticated player id."""
    if not USER_ID:
        sys.exit(
            "No player id supplied. Pass --user-id YOUR-ID or set ROLL_USER_ID.\n"
            "Find your id in the game's browser localStorage under 'user', or "
            "from the /register response."
        )
    return USER_ID


USER_ID = _resolve_user_id()

HEADERS = {
    "Content-Type": "application/json",
    **({"Authorization": f"Bearer {USER_ID}"} if USER_ID else {}),
}

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
STATE_FILE = os.path.join(os.path.dirname(__file__), f"state.{USER_ID or 'unknown'}.json")
