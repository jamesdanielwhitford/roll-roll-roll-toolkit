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

Any solo project whose name isn't one of the five above (e.g. a new
upgrade type the game adds later) isn't silently dropped: it's still
offered as a buy candidate on the same cheapest-remaining-cost rule as
Skill Up! / Weighted Die / Fast Hands, just without any hand-tuned
value judgment or sequencing. It's also excluded from
donation_gate_cleared's cap check, since we don't know if it's even
cappable - treating an unrecognized project as "must be maxed" could
block the donation gate forever if it turns out to be uncapped.
"""

SKILL_UP = "Skill Up!"
WEIGHTED_DIE = "Weighted Die"
FAST_HANDS = "Fast Hands"
LEVEL_UP = "Level Up!"
DICE_UPGRADE = "Dice Upgrade"

CAPPABLE_UPGRADES = (WEIGHTED_DIE, FAST_HANDS, LEVEL_UP, DICE_UPGRADE)

# Every solo project name this module has an opinion about, either as a
# standalone buy candidate or as part of the Level Up + Dice Upgrade
# bundle/sequencing logic.
KNOWN_UPGRADES = (SKILL_UP, WEIGHTED_DIE, FAST_HANDS, LEVEL_UP, DICE_UPGRADE)


def remaining(p):
    return max(p["goal"] - p["value"], 0)


def maxed_out(p):
    return p["maxRepeat"] is not None and p["timesCompleted"] >= p["maxRepeat"]


def _find(projects, name):
    return next((p for p in projects if p["name"] == name), None)


def unupgraded_dice_count(player):
    """Live backlog: how many of the player's current dice are still 'regular'."""
    return sum(1 for d in player["dice"] if d.get("type") != "upgraded")


def find_by_name(projects, name_query):
    """
    Case-insensitive substring match against project names, e.g. "fast"
    matches "Fast Hands". Returns the matching project dict, or None if
    no project name contains the query.
    """
    query = name_query.lower()
    return next((p for p in projects if query in p["name"].lower()), None)


def single_upgrade_candidate(projects, name_query):
    """
    Like cheapest_candidate, but restricted to one project chosen by
    name (see find_by_name) instead of picking the cheapest across all
    of them. No bundling/sequencing logic applies - even Dice Upgrade or
    Level Up! bought this way is a single-project purchase, never paired.
    Returns (cost, label, parts) or None if the name doesn't match any
    project or the match is already maxed out.
    """
    p = find_by_name(projects, name_query)
    if p is None or maxed_out(p):
        return None
    return (remaining(p), p["name"], [p])


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

    # Any solo project we don't have specific value/sequencing logic for
    # (e.g. a new upgrade type added to the game after this was written)
    # still gets bought on the same cheapest-first rule as Skill Up! /
    # Weighted Die / Fast Hands, so new upgrades aren't silently ignored.
    for p in projects:
        if p["name"] not in KNOWN_UPGRADES and not maxed_out(p):
            candidates.append((remaining(p), p["name"], [p]))

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
