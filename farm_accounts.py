"""
Registers new accounts and keeps the ones that land on the target team,
discarding the rest. Persists kept accounts to a local file so re-runs
top up toward the target instead of re-farming from zero.

Team assignment on /register appears random/round-robin across the
game's teams - there's no way to request a specific team directly, so
this just registers, checks, keeps or discards, and repeats.

Usage:
    python3 farm_accounts.py --target 30 --team "Emerald Enclave" --name "EmeraldBot"
    python3 farm_accounts.py --target 30 --team "Emerald Enclave" --name "EmeraldBot" --max-attempts 200

Accounts are named "<name>1", "<name>2", etc. Kept accounts (and their
team) persist in farmed_accounts.json, so re-running only tops up the
difference instead of starting over.
"""

import argparse
import json
import os
import time

from api import register, RollAPIError

ACCOUNTS_FILE = os.path.join(os.path.dirname(__file__), "farmed_accounts.json")


def load_accounts():
    if not os.path.exists(ACCOUNTS_FILE):
        return []
    with open(ACCOUNTS_FILE) as f:
        return json.load(f)


def save_accounts(accounts):
    with open(ACCOUNTS_FILE, "w") as f:
        json.dump(accounts, f, indent=2)


def next_username(base_name, existing_usernames):
    """base_name + incrementing number, skipping any already used/taken."""
    n = 1
    while True:
        candidate = f"{base_name}{n}"
        if candidate not in existing_usernames:
            return candidate
        n += 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, required=True, help="number of accounts to keep on the target team")
    parser.add_argument("--team", required=True, help='exact team name, e.g. "Emerald Enclave"')
    parser.add_argument("--name", required=True, help='base username, accounts are named e.g. "<name>1", "<name>2", ...')
    parser.add_argument("--max-attempts", type=int, default=500, help="safety cap on total registrations attempted")
    parser.add_argument("--delay", type=float, default=0.5, help="seconds to sleep between registrations")
    args = parser.parse_args()

    accounts = load_accounts()
    kept_for_team = [a for a in accounts if a["team"] == args.team]
    used_usernames = {a["userName"] for a in accounts}

    print(f"Already have {len(kept_for_team)}/{args.target} accounts on '{args.team}'")

    if len(kept_for_team) >= args.target:
        print("Target already met, nothing to do.")
        return

    attempts = 0
    discarded = 0

    while len(kept_for_team) < args.target and attempts < args.max_attempts:
        attempts += 1
        username = next_username(args.name, used_usernames)
        used_usernames.add(username)
        try:
            _, data = register(username)
        except RollAPIError as e:
            print(f"[attempt {attempts}] register failed for {username}: {e}")
            time.sleep(args.delay)
            continue

        player = data["player"]
        team = player["team"]

        if team == args.team:
            accounts.append({
                "userId": player["userId"],
                "userName": player["userName"],
                "team": team,
            })
            kept_for_team.append(accounts[-1])
            save_accounts(accounts)
            print(f"[attempt {attempts}] KEPT {player['userId']} ({username}) on {team} "
                  f"({len(kept_for_team)}/{args.target})")
        else:
            discarded += 1
            print(f"[attempt {attempts}] discarded {player['userId']} ({username}) on {team}")

        time.sleep(args.delay)

    print(f"\nDone. Kept {len(kept_for_team)}/{args.target} on '{args.team}'. "
          f"Attempts: {attempts}, discarded: {discarded}.")
    if len(kept_for_team) < args.target:
        print("Target not reached within --max-attempts, run again to continue topping up.")


if __name__ == "__main__":
    main()
