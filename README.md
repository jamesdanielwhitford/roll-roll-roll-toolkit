# Roll Roll Roll — scripting toolkit

Scripts to play `roll.createwithclint.com` well by automating rolls and
upgrade purchases. Everything acts only as the player whose id you supply,
never anyone else's.

## Setup

```
pip install -r requirements.txt
```

Every script needs your player id. Pass it either way:

```
python3 auto_roll.py --user-id YOUR-ID
```

or set it once per shell session:

```
export ROLL_USER_ID=YOUR-ID
python3 auto_roll.py
```

Find your id in the browser: open devtools on the game page, go to
Application -> Local Storage, and read the `user` key. It looks like
`PANDA-811100`.

Each teammate keeps their own local state file (`state.<your-id>.json`),
so you can all run this from the same clone without clobbering each
other's stats.

## Scripts

- `auto_roll.py` — rolls shortly after your cooldown expires (a random
  0.1-0.3s delay is added before each roll), forever (or `--max-rolls N` /
  `--duration SECONDS`). Add `--auto-buy` to also spend score on the
  cheapest available upgrade after every roll, `--only-upgrade NAME`
  (requires `--auto-buy`) to restrict purchases to a single project
  matched by a case-insensitive substring of its name (e.g. `fast`,
  `dice`, `skill`) instead of the cheapest-first strategy,
  `--exclude-upgrade NAME` (requires `--auto-buy`, repeatable, not
  combinable with `--only-upgrade`) to drop matching projects from the
  cheapest-first pool instead (e.g. `--exclude-upgrade skill` to never
  buy Skill Up!), `--donate-pct PCT` (default 25) to donate a slice of
  earnings to the team's group project once every cappable solo upgrade
  is maxed, and `--log FILE` to save a timestamped history.
- `upgrades.py` — shows solo project progress and the cheapest available
  buy. Manually buy one with `--contribute "Skill Up" --amount 500`.
- `stats.py` — prints session stats (rolls, score gained, rolls/min).
- `redeem.py CODE` — redeems a code you actually have. Does not guess codes.

All scripts accept `--user-id`.

## Example

```
python3 auto_roll.py --user-id YOUR-ID --auto-buy --log logs/session.log
```

Prints a line per roll:

```
[roll #7] dice=[2, 3] delta=+10 score=142 mult=2 dice=2 cooldown=6000ms [ok] | session: +108 in 228s (28/min)
[auto-buy] Skill Up! for 1110 score
[donate] 27.5 to Build Foundation
```

`score`, `mult`, `dice`, and `cooldown` reflect your live upgrade level —
they update immediately after an auto-buy, so the loop starts rolling
faster the moment a cooldown upgrade lands, no restart needed.

## Strategy notes (from API inspection + live play)

Each roll: N dice (upgradeable) are rolled. **Any single 1 among them
busts the roll and resets your current multiplier down to your floor
(`minMultiplier`).** Otherwise the dice sum is multiplied by your
current multiplier to give your score delta, and a poker-style combo on
that roll can also bump the multiplier:

| Combo | Bonus |
|---|---|
| Pair / Two Pair | none |
| Three of a Kind | +0.5 multiplier |
| Full House | +1 multiplier |
| Straight | +2 multiplier |
| Four of a Kind | +3 multiplier |
| Five of a Kind | +1 multiplier, **+1 permanent** (raises your floor) |

Because busting is so costly (it wipes your *current* multiplier, not
just the last roll's gain), bust probability compounds badly with more
dice: `P(bust) = 1 - (5/6)^dice`. At 5+ dice you're busting well over
half the time by default.

Solo projects let you spend your own score as "gold" for permanent
upgrades:

- **Level Up!** (+1 Die, repeatable up to 50x) — more dice per roll, but
  also more bust exposure, so it's only bought once every current die is
  already upgraded, paired immediately with Dice Upgrade for the new one.
- **Skill Up!** (+1 Multiplier, uncapped repeats) — direct multiplier
  increase.
- **Fast Hands** (-0.5s cooldown, max 6x) — caps at -3s off the 6s
  cooldown, up to 2x roll frequency.
- **Weighted Die** (+1% high roll odds, max 30x) — improves average roll
  value.
- **Dice Upgrade** (removes the "1" face from one die) — the cutoff on
  how many dice can be de-1'd isn't simply your dice count and can
  shift (the project can go unpurchasable in the shop below your full
  dice count), so `advisor.py` always reads the live `maxRepeat`/
  `timesCompleted` off this project rather than assuming a cap.
- **Unlock Skin** — cosmetic only, never bought automatically.

`player["dice"]` gives exact per-die ground truth
(`{"type": "regular"|"upgraded"}`), so `advisor.py` always knows the
live backlog of currently-owned dice still showing a 1. While that
backlog is nonzero and Dice Upgrade is purchasable, Dice Upgrade is
bought on its own — fixing what you have before adding more. Level Up!
only reappears (bundled with Dice Upgrade, bought back-to-back, priced
as the sum of both) once every current die is already upgraded, so a
freshly-added die is never left unprotected.

`advisor.py`'s `cheapest_candidate()` picks the buy for `--auto-buy`:
of Skill Up, Weighted Die, Fast Hands, Dice Upgrade (solo, while backlog
exists), and the Level Up + Dice Upgrade bundle (once backlog is clear),
it always buys whichever is cheapest right now, full stop. No
value/rate weighting. Every project's affordability is re-checked live
each cycle, so anything maxed out or missing from the shop simply drops
out of consideration that round.

There's also a **group** project (its name has been observed to change
over time, e.g. "Build Foundation" — found by `type == "group"`, never
by name) needing a large combined team score for a team-wide buff. A
single player's rolls won't move it alone, coordinate with your team if
you want to push it over the goal with `upgrades.py --contribute`, or
let `auto_roll.py --auto-buy` donate automatically: once Fast Hands,
Weighted Die, Level Up, and Dice Upgrade are all maxed (Skill Up! is
uncapped and stays the sole ongoing solo spend from then on),
`--donate-pct` starts skimming that percentage of each roll's earnings
into the group project, continuously, alongside normal saving.

## What this deliberately does not do

- Never uses another player's id, guessed or otherwise.
- `redeem.py` only ever submits codes you explicitly provide, it does not
  brute-force or guess promo codes.
- The auto-roller respects the server's cooldown (`nextRollTime`) instead
  of hammering the endpoint.
