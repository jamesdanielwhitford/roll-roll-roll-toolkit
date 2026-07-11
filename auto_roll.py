"""
Auto-roller: rolls the dice for YOUR OWN account the instant cooldown expires.
Optionally auto-buys upgrades, which immediately changes roll frequency
(cooldown) and per-roll value (dice/multiplier) - the loop always reads
the cooldown fresh off the latest player object, so a Fast Hands purchase
mid-run makes it start rolling faster right away.

Usage:
    python3 auto_roll.py                    # run forever, rolling only
    python3 auto_roll.py --max-rolls 50     # stop after N rolls
    python3 auto_roll.py --duration 600     # stop after N seconds
    python3 auto_roll.py --auto-buy         # also spend score on the
                                             # best-value upgrade whenever
                                             # affordable, after each roll
    python3 auto_roll.py --auto-buy --log run.log   # also append every
                                             # event to a log file for
                                             # tracking progress later
"""

import argparse
import time
import sys
from datetime import datetime

from config import require_user_id
from api import init, roll, contribute, RollAPIError
from state import load_state, save_state, record_roll
from advisor import rank_projects

POLL_SLACK_MS = 150  # small buffer so we don't hit the server exactly at cooldown edge


def now_ms():
    return int(time.time() * 1000)


def make_logger(log_path):
    if not log_path:
        return lambda msg: None

    def log(msg):
        with open(log_path, "a") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} {msg}\n")

    return log


def try_auto_buy(player, projects, log):
    """
    Saves toward and buys only the single best-value upgrade (rank #1),
    never a cheaper lower-value one, even if that's affordable sooner.
    Score has no other use in this game, so letting it sit idle while
    saving for the best upgrade costs nothing - it's simply deferred.
    Returns (updated_player, updated_projects) if a purchase happened,
    else (None, None).
    """
    ranked = rank_projects(projects, player)
    if not ranked:
        return None, None

    value, rate, cost, p = ranked[0]
    if cost > player["score"]:
        return None, None  # still saving up for the best upgrade

    msg = f"[auto-buy] {p['name']} for {cost:.0f} score (+{rate*100:.2f}% rate)"
    print(msg)
    log(msg)
    try:
        _, resp = contribute(p["id"], cost)
    except RollAPIError as e:
        err = f"[auto-buy] failed: {e}"
        print(err)
        log(err)
        return None, None
    # Real response shape: {player, projects, clientMessages: [{type, player, projects}]}
    return resp["player"], resp["projects"]


def do_roll(state, log, projects=None):
    try:
        status, data = roll()
    except RollAPIError as e:
        if e.status_code == 429:
            next_roll = None
            if isinstance(e.payload, dict):
                next_roll = e.payload.get("nextRollTime")
            msg = f"[cooldown] roll rejected, nextRollTime={next_roll}"
            print(msg)
            log(msg)
            return next_roll, None
        if e.status_code == 403:
            print("[error] registration required for this userId")
            sys.exit(1)
        msg = f"[error] roll failed: {e}"
        print(msg)
        log(msg)
        return now_ms() + 3000, None  # back off 3s on unexpected errors

    messages = data.get("clientMessages", [])
    score_update = next((m for m in messages if m["type"] == "s-score-update"), None)
    roll_success = next((m for m in messages if m["type"] == "s-roll-success"), None)

    if roll_success:
        player = roll_success["player"]
        delta = score_update["delta"] if score_update else 0
        is_bust = roll_success.get("isBust", False)
        values = [v["roll"] for v in roll_success.get("values", [])]
        record_roll(state, player, delta, is_bust)

        tag = "BUST" if is_bust else "ok"
        stats = state["stats"]
        elapsed = max(time.time() - stats["session_start"], 0.001)
        rate = stats["total_score_gained"] / elapsed * 60
        msg = (
            f"[roll #{stats['total_rolls']}] dice={values} "
            f"delta={delta:+g} score={player['score']:g} mult={player['multiplier']} "
            f"dice={len(player['dice'])} cooldown={player['rollCooldownMs']}ms [{tag}] "
            f"| session: +{stats['total_score_gained']:g} in {elapsed:.0f}s ({rate:.0f}/min)"
        )
        if projects:
            ranked = rank_projects(projects, player)
            if ranked:
                _, _, top_cost, top_p = ranked[0]
                remaining_cost = max(top_cost - player["score"], 0)
                if remaining_cost > 0:
                    msg += f" | saving for {top_p['name']}: {player['score']:g}/{top_cost:.0f}"
        print(msg)
        log(msg)
        return player["nextRollTime"], player

    msg = f"[warn] unexpected response: {data}"
    print(msg)
    log(msg)
    return now_ms() + 3000, None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", metavar="ID", default=None, help="your player id (or set ROLL_USER_ID)")
    parser.add_argument("--max-rolls", type=int, default=None)
    parser.add_argument("--duration", type=float, default=None, help="seconds")
    parser.add_argument("--auto-buy", action="store_true", help="spend score on best-value upgrades as you go")
    parser.add_argument("--log", metavar="FILE", default=None, help="append events to this log file")
    args = parser.parse_args()
    require_user_id()

    log = make_logger(args.log)
    state = load_state()

    # Bootstrap: find out current cooldown state and project list.
    _, data = init()
    player = data["player"]
    projects = data["projects"]
    next_roll_time = player.get("nextRollTime")
    state["player"] = player
    save_state(state)

    start_msg = f"Starting auto-roll for {player['userName']} ({player['userId']}), score={player['score']}, auto_buy={args.auto_buy}"
    print(start_msg)
    log(start_msg)

    start_time = time.time()
    rolls_done = 0

    while True:
        if args.max_rolls is not None and rolls_done >= args.max_rolls:
            print("Reached max-rolls limit, stopping.")
            break
        if args.duration is not None and (time.time() - start_time) >= args.duration:
            print("Reached duration limit, stopping.")
            break

        if next_roll_time is not None:
            wait_ms = next_roll_time - now_ms() + POLL_SLACK_MS
            if wait_ms > 0:
                time.sleep(wait_ms / 1000)

        next_roll_time, rolled_player = do_roll(state, log, projects if args.auto_buy else None)
        rolls_done += 1

        if rolled_player is not None:
            player = rolled_player

        if args.auto_buy and player is not None:
            bought_player, bought_projects = try_auto_buy(player, projects, log)
            if bought_player is not None:
                player = bought_player
                projects = bought_projects
                state["player"] = player
                save_state(state)
                # Cooldown/dice/multiplier may have just changed - recompute
                # the wait from the freshest player state we have.
                next_roll_time = player.get("nextRollTime", next_roll_time)

        if next_roll_time is None:
            time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
