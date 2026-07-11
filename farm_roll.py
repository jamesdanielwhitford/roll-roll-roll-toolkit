"""
Rolls concurrently for every account in farmed_accounts.json (see
farm_accounts.py), each on its own cooldown timer. Same auto-buy logic
as auto_roll.py, applied independently per account.

Usage:
    python3 farm_roll.py
    python3 farm_roll.py --auto-buy
    python3 farm_roll.py --team "Emerald Enclave"   # only roll accounts on this team
"""

import argparse
import json
import os
import threading
import time

import requests

from config import BASE_URL
from advisor import rank_projects

ACCOUNTS_FILE = os.path.join(os.path.dirname(__file__), "farmed_accounts.json")
POLL_SLACK_MS = 150


def load_accounts(team_filter=None):
    if not os.path.exists(ACCOUNTS_FILE):
        return []
    with open(ACCOUNTS_FILE) as f:
        accounts = json.load(f)
    if team_filter:
        accounts = [a for a in accounts if a["team"] == team_filter]
    return accounts


def headers_for(user_id):
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {user_id}",
    }


def now_ms():
    return int(time.time() * 1000)


def roll_loop(account, auto_buy, print_lock):
    user_id = account["userId"]
    headers = headers_for(user_id)

    try:
        r = requests.get(f"{BASE_URL}/init", headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as e:
        with print_lock:
            print(f"[{user_id}] init failed: {e}")
        return

    player = data["player"]
    projects = data["projects"]
    next_roll_time = player.get("nextRollTime")

    while True:
        if next_roll_time is not None:
            wait_ms = next_roll_time - now_ms() + POLL_SLACK_MS
            if wait_ms > 0:
                time.sleep(wait_ms / 1000)

        try:
            r = requests.post(f"{BASE_URL}/roll", headers=headers, timeout=15)
        except requests.RequestException as e:
            with print_lock:
                print(f"[{user_id}] roll error: {e}")
            time.sleep(3)
            continue

        if r.status_code == 429:
            payload = r.json() if r.content else {}
            next_roll_time = payload.get("nextRollTime")
            continue
        if r.status_code == 403:
            with print_lock:
                print(f"[{user_id}] registration required, stopping this account")
            return
        if r.status_code >= 400:
            with print_lock:
                print(f"[{user_id}] roll failed {r.status_code}: {r.text}")
            time.sleep(3)
            continue

        resp = r.json()
        messages = resp.get("clientMessages", [])
        score_update = next((m for m in messages if m["type"] == "s-score-update"), None)
        roll_success = next((m for m in messages if m["type"] == "s-roll-success"), None)

        if not roll_success:
            time.sleep(3)
            continue

        player = roll_success["player"]
        delta = score_update["delta"] if score_update else 0
        with print_lock:
            print(f"[{user_id}] score={player['score']:g} delta={delta:+g} "
                  f"dice={len(player['dice'])} mult={player['multiplier']}")

        if auto_buy:
            ranked = rank_projects(projects, player)
            if ranked:
                value, rate, cost, p = ranked[0]
                if cost <= player["score"]:
                    try:
                        cr = requests.post(
                            f"{BASE_URL}/project/contribute",
                            headers=headers,
                            json={"projectId": p["id"], "amount": cost},
                            timeout=15,
                        )
                        cr.raise_for_status()
                        cdata = cr.json()
                        player = cdata["player"]
                        projects = cdata["projects"]
                        with print_lock:
                            print(f"[{user_id}] auto-buy {p['name']} for {cost:.0f} "
                                  f"(+{rate*100:.2f}% rate)")
                    except requests.RequestException as e:
                        with print_lock:
                            print(f"[{user_id}] auto-buy failed: {e}")

        next_roll_time = player.get("nextRollTime")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--auto-buy", action="store_true")
    parser.add_argument("--team", default=None, help="only roll accounts on this team")
    parser.add_argument("--exclude-user-id", action="append", default=[],
                         help="skip this account (e.g. one you're already rolling elsewhere); repeatable")
    args = parser.parse_args()

    accounts = load_accounts(team_filter=args.team)
    if args.exclude_user_id:
        accounts = [a for a in accounts if a["userId"] not in args.exclude_user_id]
    if not accounts:
        print(f"No accounts found in {ACCOUNTS_FILE}. Run farm_accounts.py first.")
        return

    print(f"Rolling for {len(accounts)} accounts (auto_buy={args.auto_buy})")

    print_lock = threading.Lock()
    threads = []
    for account in accounts:
        t = threading.Thread(target=roll_loop, args=(account, args.auto_buy, print_lock), daemon=True)
        t.start()
        threads.append(t)
        time.sleep(0.2)  # stagger startup so init calls don't all fire at once

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
