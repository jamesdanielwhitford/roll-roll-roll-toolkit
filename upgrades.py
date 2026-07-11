"""
Shows current solo project progress and tells you which upgrade is
"cheapest per point of score" right now, i.e. where to spend contributions.

The game exposes solo projects like:
  Level Up!    -> +1 Die            (repeatable, goal grows)
  Skill Up!    -> +1 Multiplier     (repeatable, goal grows)
  Fast Hands   -> -0.5s Cooldown    (max 6 times)
  Weighted Die -> +1% high-roll odds (max 30 times)
  Unlock Skin  -> cosmetic           (max 6 times)

Contribution uses your own score as "gold" (POST /project/contribute).
This script just reports state; it does not auto-spend without --commit.
"""

import argparse
from config import require_user_id
from api import init, contribute, RollAPIError
from advisor import remaining, maxed_out, rank_projects


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", metavar="ID", default=None, help="your player id (or set ROLL_USER_ID)")
    parser.add_argument("--contribute", metavar="PROJECT_NAME", help="Substring match of project name to contribute to")
    parser.add_argument("--amount", type=float, help="Amount of score/gold to contribute")
    args = parser.parse_args()
    require_user_id()

    _, data = init()
    player = data["player"]
    projects = [p for p in data["projects"] if p["type"] == "solo"]

    print(f"{player['userName']} ({player['userId']}) — score={player['score']:g}\n")
    print(f"{'Project':<16} {'Effect':<32} {'Progress':>16} {'Remaining':>10} {'Done/Max':>10}")
    print("-" * 90)
    for p in projects:
        status = "MAXED" if maxed_out(p) else ""
        max_repeat = p["maxRepeat"] if p["maxRepeat"] is not None else "inf"
        print(
            f"{p['name']:<16} {p['description']:<32} "
            f"{p['value']:>7.0f}/{p['goal']:<7.0f} {remaining(p):>10.0f} "
            f"{p['timesCompleted']:>4}/{max_repeat:<5} {status}"
        )

    ranked = rank_projects(projects, player)
    if ranked:
        print("\nBest value right now (rate increase per point spent):")
        for value, rate, cost, p in ranked:
            print(f"  {p['name']:<16} +{rate*100:.2f}% rate for {cost:.0f} score (value={value:.6f})")

    if args.contribute:
        match = [p for p in projects if args.contribute.lower() in p["name"].lower()]
        if not match:
            print(f"\nNo project matches '{args.contribute}'")
            return
        target = match[0]
        if maxed_out(target):
            print(f"\n{target['name']} is already maxed out.")
            return
        amount = args.amount if args.amount is not None else remaining(target)
        if amount > player["score"]:
            print(f"\nNot enough score: have {player['score']:g}, need {amount:g}")
            return
        print(f"\nContributing {amount:g} to {target['name']}...")
        try:
            status, resp = contribute(target["id"], amount)
            new_player = resp["player"]
            print(f"Done. New score={new_player['score']:g}, "
                  f"dice={len(new_player['dice'])}, mult={new_player['multiplier']}, "
                  f"cooldown={new_player['rollCooldownMs']}ms")
        except RollAPIError as e:
            print(f"Failed: {e}")


if __name__ == "__main__":
    main()
