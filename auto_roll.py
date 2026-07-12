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
                                             # cheapest available upgrade
                                             # whenever affordable, after
                                             # each roll
    python3 auto_roll.py --auto-buy --log run.log   # also append every
                                             # event to a log file for
                                             # tracking progress later
"""

import argparse
import random
import time
import sys
from datetime import datetime

import requests

from config import require_user_id
from api import init, roll, contribute, RollAPIError
from state import load_state, save_state, record_roll
from advisor import cheapest_candidate, single_upgrade_candidate, find_by_name, remaining, find_group_project, donation_gate_cleared

RETRY_BACKOFF_S = 5  # wait this long after a transient network/server error before retrying

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


def try_auto_buy(player, projects, log, only_upgrade=None):
    """
    Saves toward and buys whichever of the four candidates (Skill Up,
    Weighted Die, Fast Hands, or the Level Up + Dice Upgrade bundle) is
    cheapest right now, purely by cost - no value/rate weighting.
    Score has no other use in this game, so letting it sit idle while
    saving costs nothing, it's simply deferred.

    If `only_upgrade` is set, restricts entirely to the single project
    matching that name (see advisor.find_by_name) instead - saves toward
    and repeatedly buys just that one, ignoring every other candidate
    and all bundling/sequencing logic.

    Returns (updated_player, updated_projects) if a purchase happened,
    else (None, None).
    """
    if only_upgrade is not None:
        candidate = single_upgrade_candidate(projects, only_upgrade)
    else:
        candidate = cheapest_candidate(projects, player)
    if candidate is None:
        return None, None

    cost, label, parts = candidate
    if cost > player["score"]:
        return None, None  # still saving up for the cheapest candidate

    msg = f"[auto-buy] {label} for {cost:.0f} score"
    print(msg)
    log(msg)

    result_player, result_projects = None, None
    for p in parts:
        try:
            _, resp = contribute(p["id"], remaining(p))
        except (RollAPIError, requests.RequestException) as e:
            err = f"[auto-buy] failed on {p['name']}: {e}"
            print(err)
            log(err)
            break
        # Real response shape: {player, projects, clientMessages: [{type, player, projects}]}
        result_player, result_projects = resp["player"], resp["projects"]

    return result_player, result_projects


def try_donate(player, projects, delta, donate_pct, log):
    """
    Once every genuinely cappable solo upgrade is maxed (see
    donation_gate_cleared), Skill Up! is the only solo spend left, so
    donate_pct% of each roll's score gain goes straight to the team's
    current group project instead - a continuous slice alongside normal
    saving, not a switch away from it. Returns (updated_player,
    updated_projects) if a donation happened, else (None, None).
    """
    if donate_pct <= 0 or delta <= 0 or not donation_gate_cleared(projects):
        return None, None

    group_project = find_group_project(projects)
    if group_project is None:
        return None, None

    donation = min(delta * (donate_pct / 100), player["score"])
    if donation <= 0:
        return None, None

    msg = f"[donate] {donation:.1f} to {group_project['name']}"
    print(msg)
    log(msg)
    try:
        _, resp = contribute(group_project["id"], donation)
    except (RollAPIError, requests.RequestException) as e:
        err = f"[donate] failed: {e}"
        print(err)
        log(err)
        return None, None
    return resp["player"], resp["projects"]


def init_with_retry(log):
    """
    Bootstrap call at startup. Cloudflare/origin hiccups (5xx) and plain
    network errors (timeouts, connection resets) are transient - retry
    with backoff instead of crashing before the loop even starts.
    """
    while True:
        try:
            return init()
        except RollAPIError as e:
            if e.status_code == 403:
                print("[error] registration required for this userId")
                sys.exit(1)
            msg = f"[error] init failed ({e}), retrying in {RETRY_BACKOFF_S}s"
        except requests.RequestException as e:
            msg = f"[error] init failed ({e}), retrying in {RETRY_BACKOFF_S}s"
        print(msg)
        log(msg)
        time.sleep(RETRY_BACKOFF_S)


def do_roll(state, log, projects=None, only_upgrade=None):
    time.sleep(random.uniform(0.5, 1.0))
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
            return next_roll, None, 0
        if e.status_code == 403:
            print("[error] registration required for this userId")
            sys.exit(1)
        msg = f"[error] roll failed: {e}"
        print(msg)
        log(msg)
        return now_ms() + RETRY_BACKOFF_S * 1000, None, 0  # back off on unexpected errors
    except requests.RequestException as e:
        msg = f"[error] roll request failed: {e}"
        print(msg)
        log(msg)
        return now_ms() + RETRY_BACKOFF_S * 1000, None, 0  # back off on network/timeout errors

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
            if only_upgrade is not None:
                candidate = single_upgrade_candidate(projects, only_upgrade)
            else:
                candidate = cheapest_candidate(projects, player)
            if candidate is not None:
                top_cost, top_label, _ = candidate
                remaining_cost = max(top_cost - player["score"], 0)
                if remaining_cost > 0:
                    msg += f" | saving for {top_label}: {player['score']:g}/{top_cost:.0f}"
        print(msg)
        log(msg)
        return player["nextRollTime"], player, delta

    msg = f"[warn] unexpected response: {data}"
    print(msg)
    log(msg)
    return now_ms() + 3000, None, 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", metavar="ID", default=None, help="your player id (or set ROLL_USER_ID)")
    parser.add_argument("--max-rolls", type=int, default=None)
    parser.add_argument("--duration", type=float, default=None, help="seconds")
    parser.add_argument("--auto-buy", action="store_true", help="spend score on the cheapest available upgrade as you go")
    parser.add_argument("--only-upgrade", metavar="NAME", default=None,
                         help="with --auto-buy, restrict purchases to the single project whose "
                              "name contains NAME (case-insensitive, e.g. 'fast', 'dice', 'skill'), "
                              "instead of the cheapest-first strategy")
    parser.add_argument("--donate-pct", type=float, default=25.0,
                         help="percent of each roll's score gain to donate to the team's current "
                              "group project, once every cappable solo upgrade is maxed out "
                              "(default 25, 0 disables donations)")
    parser.add_argument("--log", metavar="FILE", default=None, help="append events to this log file")
    args = parser.parse_args()
    if args.only_upgrade is not None and not args.auto_buy:
        parser.error("--only-upgrade requires --auto-buy")
    require_user_id()

    log = make_logger(args.log)
    state = load_state()

    # Bootstrap: find out current cooldown state and project list.
    _, data = init_with_retry(log)
    player = data["player"]
    projects = data["projects"]
    next_roll_time = player.get("nextRollTime")
    state["player"] = player
    save_state(state)

    if args.only_upgrade is not None and find_by_name(projects, args.only_upgrade) is None:
        names = ", ".join(p["name"] for p in projects)
        print(f"[error] no project matches --only-upgrade '{args.only_upgrade}'. Available: {names}")
        sys.exit(1)

    start_msg = f"Starting auto-roll for {player['userName']} ({player['userId']}), score={player['score']}, auto_buy={args.auto_buy}"
    if args.only_upgrade is not None:
        start_msg += f", only_upgrade={args.only_upgrade!r}"
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

        next_roll_time, rolled_player, delta = do_roll(
            state, log, projects if args.auto_buy else None, args.only_upgrade
        )
        rolls_done += 1

        if rolled_player is not None:
            player = rolled_player

        if player is not None:
            donated_player, donated_projects = try_donate(player, projects, delta, args.donate_pct, log)
            if donated_player is not None:
                player = donated_player
                projects = donated_projects
                state["player"] = player
                save_state(state)
                next_roll_time = player.get("nextRollTime", next_roll_time)

        if args.auto_buy and player is not None:
            bought_player, bought_projects = try_auto_buy(player, projects, log, args.only_upgrade)
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
