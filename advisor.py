"""
Value model for solo upgrade projects: estimates the proportional
increase to score-per-second each project's *next* purchase would give,
then ranks projects by (rate increase / cost) so the best-value buy is
always obvious.

Effects, from the project descriptions returned by /init:
  Level Up!    +1 Die             -> +1/current_dice_count to avg roll sum
  Skill Up!    +1 Multiplier      -> (mult+1)/mult multiplicative increase
  Fast Hands   -0.5s Cooldown     -> cooldown/(cooldown-500) freq increase
  Weighted Die +1% high-roll odds -> small flat bump, hard to quantify
                                      precisely without the odds table,
                                      treated as a conservative constant
  Unlock Skin  cosmetic           -> excluded, no effect on score rate
"""

WEIGHTED_DIE_RATE_BONUS = 0.01  # conservative estimate: +1% avg roll value


def remaining(p):
    return max(p["goal"] - p["value"], 0)


def maxed_out(p):
    return p["maxRepeat"] is not None and p["timesCompleted"] >= p["maxRepeat"]


def rate_multiplier(project_name, player):
    """Proportional increase to score-per-second from buying this project once more."""
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
    return 0.0  # Unlock Skin and anything else: no score-rate effect


def rank_projects(projects, player):
    """
    Returns solo, non-cosmetic, non-maxed projects sorted by value
    (rate increase per point of remaining cost spent), best first.
    """
    ranked = []
    for p in projects:
        if p["type"] != "solo" or p["name"] == "Unlock Skin" or maxed_out(p):
            continue
        cost = remaining(p)
        if cost <= 0:
            continue
        rate = rate_multiplier(p["name"], player)
        value = rate / cost
        ranked.append((value, rate, cost, p))
    ranked.sort(key=lambda t: t[0], reverse=True)
    return ranked
