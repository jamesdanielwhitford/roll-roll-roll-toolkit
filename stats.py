"""
Prints a summary of session stats tracked in state.json, and dumps
current player snapshot. Run any time to check progress.
"""

import time
from state import load_state


def main():
    state = load_state()
    stats = state["stats"]
    player = state["player"]

    if not player:
        print("No data yet, run auto_roll.py or upgrades.py first.")
        return

    print(f"Player: {player['userName']} ({player['userId']})")
    print(f"Team: {player['team']}")
    print(f"Score: {player['score']:g}")
    print(f"Dice: {len(player['dice'])} x {[d['type'] for d in player['dice']]}")
    print(f"Multiplier: {player['multiplier']}")
    print(f"Cooldown: {player['rollCooldownMs']}ms")
    print()
    print(f"Total rolls this session: {stats['total_rolls']}")
    print(f"Total score gained: {stats['total_score_gained']:g}")
    print(f"Busts: {stats['busts']}")

    if stats["session_start"]:
        elapsed = time.time() - stats["session_start"]
        if elapsed > 0 and stats["total_rolls"] > 0:
            print(f"Elapsed: {elapsed:.0f}s")
            print(f"Rolls/min: {stats['total_rolls'] / elapsed * 60:.1f}")
            print(f"Score/min: {stats['total_score_gained'] / elapsed * 60:.1f}")


if __name__ == "__main__":
    main()
