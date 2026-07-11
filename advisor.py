"""
Value model for solo upgrade projects: estimates the proportional
increase to score-per-second each project's *next* purchase would give,
then ranks projects by (rate increase / cost) so the best-value buy is
always obvious.

Effects, from the project descriptions returned by /init:
  Level Up!     +1 Die             -> +1/current_dice_count to avg roll sum
  Skill Up!     +1 Multiplier      -> (mult+1)/mult multiplicative increase
  Fast Hands    -0.5s Cooldown     -> cooldown/(cooldown-500) freq increase
  Weighted Die  +1% high-roll odds -> small flat bump, hard to quantify
                                       precisely without the odds table,
                                       treated as a conservative constant
  Dice Upgrade  Remove "1" from a die -> see below, simulated
  Unlock Skin   cosmetic           -> excluded, no effect on score rate

Dice Upgrade is fundamentally different from the others: rolling any
single 1 among your dice busts the roll and resets your *current*
multiplier down to your floor (minMultiplier). Removing the 1 from a
die means that die can never trigger a bust. Because bust probability
is 1 - (5/6)^(dice still showing 1), each de-1'd die multiplies your
survival odds rather than adding to them - and the higher your current
multiplier climbs above your floor, the more a bust costs you, so this
upgrade's value is state-dependent (rises as your multiplier pulls
ahead of your floor) rather than a fixed percentage. We estimate it by
Monte Carlo simulation of expected multiplier change per roll, with and
without the extra de-1'd die, using your live multiplier/floor/dice
count.

Combo bonuses (poker-style hand on the dice each roll, once you survive
the 1-check): Three of a Kind +0.5, Full House +1, Straight +2, Four of
a Kind +3, Five of a Kind +1 current and +1 permanent (raises floor).
Pair / Two Pair: no bonus.
"""

import random
from collections import Counter

WEIGHTED_DIE_RATE_BONUS = 0.01  # conservative estimate: +1% avg roll value
DICE_UPGRADE_TRIALS = 20000


def remaining(p):
    return max(p["goal"] - p["value"], 0)


def maxed_out(p):
    return p["maxRepeat"] is not None and p["timesCompleted"] >= p["maxRepeat"]


def _combo_bonus(dice_values):
    """(current_mult_bonus, permanent_mult_bonus) for one roll's dice values (no 1s)."""
    n = len(dice_values)
    counts = sorted(Counter(dice_values).values(), reverse=True)
    is_straight = len(set(dice_values)) == n and (max(dice_values) - min(dice_values) == n - 1) and n >= 5

    if counts[0] == 5:
        return 1.0, 1.0
    if n >= 4 and counts[0] == 4:
        return 3.0, 0.0
    if is_straight:
        return 2.0, 0.0
    if n >= 5 and counts[0] == 3 and len(counts) > 1 and counts[1] == 2:
        return 1.0, 0.0
    if counts[0] == 3:
        return 0.5, 0.0
    return 0.0, 0.0


def _expected_mult_change_per_roll(n_dice, k_fixed, mult, min_mult, trials=DICE_UPGRADE_TRIALS, seed=0):
    """
    Simulates one roll: k_fixed dice can't show 1 (faces 2-6), the rest are
    normal d6. Returns expected change to *current* multiplier per roll:
    on bust, multiplier resets to min_mult; on survive, it gains the combo bonus.
    """
    rng = random.Random(seed)
    risky = n_dice - k_fixed
    survive_count = 0
    bonus_sum = 0.0

    for _ in range(trials):
        risky_rolls = [rng.randint(1, 6) for _ in range(risky)]
        if 1 in risky_rolls:
            continue
        survive_count += 1
        fixed_rolls = [rng.randint(2, 6) for _ in range(k_fixed)]
        bonus, _perm = _combo_bonus(tuple(risky_rolls + fixed_rolls))
        bonus_sum += bonus

    p_survive = survive_count / trials
    p_bust = 1 - p_survive
    avg_bonus_given_survive = (bonus_sum / survive_count) if survive_count else 0.0
    return p_survive * avg_bonus_given_survive + p_bust * (min_mult - mult)


def dice_upgrade_rate(player, k_fixed):
    """
    Value of buying the next Dice Upgrade (going from k_fixed to k_fixed+1
    fixed dice). k_fixed should be the project's timesCompleted (the API
    tracks purchases, not per-die state, but each purchase fixes exactly
    one more die so the counts line up).

    Pure one-step marginal value understates this upgrade: the real payoff
    is completing ALL dice, which makes busting impossible and turns your
    multiplier into an uncapped climb instead of a lossy random walk. A
    step-by-step ranking would keep underrating early purchases relative
    to that end state. So this blends two components:
      - marginal: the immediate one-step improvement (same style as before)
      - completion: a share of the value of reaching the fully-fixed state
        from here, weighted toward the *last* remaining purchases (since
        those are what actually flips you into the uncapped regime)
    """
    n_dice = len(player["dice"])
    mult = player["multiplier"]
    min_mult = player["minMultiplier"]
    k_fixed = min(k_fixed, n_dice)

    if n_dice == 0 or k_fixed >= n_dice:
        return 0.0  # no unfixed dice left to upgrade

    before = _expected_mult_change_per_roll(n_dice, k_fixed, mult, min_mult, seed=1)
    after = _expected_mult_change_per_roll(n_dice, k_fixed + 1, mult, min_mult, seed=1)
    fully_fixed = _expected_mult_change_per_roll(n_dice, n_dice, mult, min_mult, seed=1)

    if before <= 0 and after <= 0:
        marginal = after - before
    elif before <= 0 < after:
        marginal = abs(before) + after
    else:
        marginal = (after - before) / abs(before) if before != 0 else after

    # How much of the "fully fixed" payoff does this purchase unlock?
    # remaining_after_this = dice still risky once this purchase lands.
    # Weight rises as remaining_after_this shrinks, so the last purchase
    # (remaining_after_this == 0) gets the full completion bonus, and the
    # first purchase on a high dice count gets very little of it.
    remaining_after_this = n_dice - (k_fixed + 1)
    total_unfixed_now = n_dice - k_fixed
    completion_share = 1 - (remaining_after_this / total_unfixed_now)
    completion_bonus = max(fully_fixed - before, 0) * completion_share

    return marginal + completion_bonus


def rate_multiplier(project, player):
    """Proportional increase to score-per-second from buying this project once more."""
    project_name = project["name"]
    dice_count = len(player["dice"])
    mult = player["multiplier"]
    cooldown = player["rollCooldownMs"]

    if project_name == "Level Up!":
        return (dice_count + 1) / dice_count - 1
    if project_name == "Skill Up!":
        return (mult + 1) / mult - 1
    if project_name == "Fast Hands":
        new_cooldown = max(cooldown - 500, 500)
        return cooldown / new_cooldown - 1
    if project_name == "Weighted Die":
        return WEIGHTED_DIE_RATE_BONUS
    if project_name == "Dice Upgrade":
        return dice_upgrade_rate(player, project["timesCompleted"])
    return 0.0  # Unlock Skin and anything else: no score-rate effect


def rank_projects(projects, player):
    """
    Returns solo, non-cosmetic, non-maxed projects sorted by value
    (rate increase per point of remaining cost spent), best first.
    Dice Upgrade is skipped once timesCompleted reaches your current dice
    count (no unfixed dice left to buy for).
    """
    ranked = []
    for p in projects:
        if p["type"] != "solo" or p["name"] == "Unlock Skin" or maxed_out(p):
            continue
        if p["name"] == "Dice Upgrade" and p["timesCompleted"] >= len(player["dice"]):
            continue
        cost = remaining(p)
        if cost <= 0:
            continue
        rate = rate_multiplier(p, player)
        value = rate / cost
        ranked.append((value, rate, cost, p))
    ranked.sort(key=lambda t: t[0], reverse=True)
    return ranked
