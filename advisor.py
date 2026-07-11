"""
Buy-decision model for solo upgrade projects.

Fixed strategy: of the game's four levers, buy whichever is cheapest
right now, full stop, no value/rate weighting.

  - Skill Up!     (+1 Multiplier)
  - Weighted Die  (+1% high-roll odds)
  - Fast Hands    (-0.5s Cooldown)
  - Dice Upgrade / Level Up!, sequenced: player["dice"] gives exact
    per-die ground truth ({"type": "regular"|"upgraded"}), so we always
    know the live backlog of currently-owned dice that still show a 1.
    While that backlog is > 0 and Dice Upgrade is still purchasable,
    Dice Upgrade is offered solo (fix what you have before adding more).
    Only once every current die is upgraded (backlog == 0) does buying a
    new die become safe, so Level Up! then only appears bundled with
    Dice Upgrade, bought back-to-back as a single unit (priced as the
    sum of both) so the new die never sits unprotected.

All caps (Fast Hands maxRepeat 6x, Weighted Die 30x, Level Up 50x, and
notably Dice Upgrade's cutoff on how many dice can be de-1'd) are read
live from each project's own maxRepeat/timesCompleted fields returned by
the API, never assumed - the Dice Upgrade project can itself become
unpurchasable below your full dice count (a shop-side cap that's been
observed to shift), which is exactly why the per-die backlog check needs
to also confirm Dice Upgrade is actually available, not just that
backlog exists.

Once the four genuinely cappable upgrades (Fast Hands, Weighted Die,
Level Up, Dice Upgrade) are all maxed - Skill Up! is uncapped and
excluded from this check, it can never be "maxed" - the only solo spend
left is Skill Up!, so from then on auto_roll.py also donates a slice of
each roll's earnings to the team's current group project (see
find_group_project / donation_gate_cleared) while the rest keeps
flowing into savings as before.
"""

SKILL_UP = "Skill Up!"
WEIGHTED_DIE = "Weighted Die"
FAST_HANDS = "Fast Hands"
LEVEL_UP = "Level Up!"
DICE_UPGRADE = "Dice Upgrade"

CAPPABLE_UPGRADES = (WEIGHTED_DIE, FAST_HANDS, LEVEL_UP, DICE_UPGRADE)


def remaining(p):
    return max(p["goal"] - p["value"], 0)


def maxed_out(p):
    return p["maxRepeat"] is not None and p["timesCompleted"] >= p["maxRepeat"]


def _find(projects, name):
    return next((p for p in projects if p["name"] == name), None)


def unupgraded_dice_count(player):
    """Live backlog: how many of the player's current dice are still 'regular'."""
    return sum(1 for d in player["dice"] if d.get("type") != "upgraded")


def cheapest_candidate(projects, player):
    """
    Returns (cost, label, parts) for the cheapest currently-purchasable
    candidate, or None if nothing qualifies. `parts` is the list of
    project dicts to buy, in order (length 1 normally, length 2 for the
    Level Up + Dice Upgrade bundle).
    """
    candidates = []

    for name in (SKILL_UP, WEIGHTED_DIE, FAST_HANDS):
        p = _find(projects, name)
        if p is not None and not maxed_out(p):
            candidates.append((remaining(p), name, [p]))

    dice_upgrade = _find(projects, DICE_UPGRADE)
    dice_upgrade_available = dice_upgrade is not None and not maxed_out(dice_upgrade)
    backlog = unupgraded_dice_count(player)

    if backlog > 0:
        # Existing dice still show a 1 - fix those before adding more.
        if dice_upgrade_available:
            candidates.append((remaining(dice_upgrade), DICE_UPGRADE, [dice_upgrade]))
    else:
        # Every current die is already upgraded - safe to add a new one,
        # paired immediately with upgrading it.
        level_up = _find(projects, LEVEL_UP)
        if level_up is not None and dice_upgrade_available and not maxed_out(level_up):
            bundle_cost = remaining(level_up) + remaining(dice_upgrade)
            candidates.append((bundle_cost, f"{LEVEL_UP} + {DICE_UPGRADE}", [level_up, dice_upgrade]))

    if not candidates:
        return None
    candidates.sort(key=lambda t: t[0])
    return candidates[0]


def find_group_project(projects):
    """
    Returns the current active team/collective project, if any. Looked
    up by type == "group", not by name - the collective goal's name has
    been observed to change over time, so name matching would silently
    break. There's at most one live group project at a time (the next
    tier unlocks once the current one completes).
    """
    for p in projects:
        if p.get("type") == "group" and not maxed_out(p):
            return p
    return None


def donation_gate_cleared(projects):
    """
    True once every genuinely cappable solo upgrade (Fast Hands,
    Weighted Die, Level Up, Dice Upgrade) is maxed out live per the API.
    Skill Up! is uncapped and deliberately excluded, otherwise this
    could never fire. Once cleared, Skill Up! is the only solo spend
    left, so the rest of each roll's earnings can usefully go toward the
    group project instead of sitting idle.
    """
    for name in CAPPABLE_UPGRADES:
        p = _find(projects, name)
        if p is None or not maxed_out(p):
            return False
    return True
