"""
Local persisted state: last known player snapshot + running stats.
"""

import json
import os
import time
from config import STATE_FILE

DEFAULT_STATE = {
    "player": None,
    "stats": {
        "total_rolls": 0,
        "total_score_gained": 0,
        "busts": 0,
        "session_start": None,
    },
}


def load_state():
    if not os.path.exists(STATE_FILE):
        return json.loads(json.dumps(DEFAULT_STATE))
    with open(STATE_FILE) as f:
        return json.load(f)


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def record_roll(state, player, delta, is_bust):
    state["player"] = player
    state["stats"]["total_rolls"] += 1
    state["stats"]["total_score_gained"] += delta
    if is_bust:
        state["stats"]["busts"] += 1
    if state["stats"]["session_start"] is None:
        state["stats"]["session_start"] = time.time()
    save_state(state)
