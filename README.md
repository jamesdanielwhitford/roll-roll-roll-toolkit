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

- `auto_roll.py` — rolls the instant your cooldown expires, forever (or
  `--max-rolls N` / `--duration SECONDS`). Add `--auto-buy` to also spend
  score on the best-value upgrade after every roll, and `--log FILE` to
  save a timestamped history.
- `upgrades.py` — shows solo project progress and a ranked "best value"
  list. Manually buy one with `--contribute "Skill Up" --amount 500`.
- `stats.py` — prints session stats (rolls, score gained, rolls/min).
- `redeem.py CODE` — redeems a code you actually have. Does not guess codes.
- `farm_accounts.py` — registers new accounts, keeps the ones landing on
  a target team and discards the rest, persisting kept accounts to
  `farmed_accounts.json`. Re-running only tops up toward `--target`
  instead of starting over. Team assignment observed as strict
  round-robin across the game's teams, not random.
- `farm_roll.py` — rolls concurrently (one thread per account) for every
  account in `farmed_accounts.json`, each on its own cooldown. Supports
  `--auto-buy` (same ranking logic as `auto_roll.py`, applied per
  account) and `--team` / `--exclude-user-id` filters.

All single-account scripts accept `--user-id`. `farm_accounts.py` needs
no id (it registers fresh accounts); `farm_roll.py` reads ids from
`farmed_accounts.json`.

## Example

```
python3 auto_roll.py --user-id YOUR-ID --auto-buy --log logs/session.log
```

Prints a line per roll:

```
[roll #7] dice=[2, 3] delta=+10 score=142 mult=2 dice=2 cooldown=6000ms [ok] | session: +108 in 228s (28/min)
[auto-buy] Skill Up! for 1110 score (+50.00% rate)
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
  also more bust exposure until you pair it with Dice Upgrade.
- **Skill Up!** (+1 Multiplier, uncapped repeats) — direct multiplier
  increase. Note: it's not yet confirmed via testing whether this also
  raises your floor (`minMultiplier`) or only your current multiplier —
  the model conservatively assumes the latter.
- **Fast Hands** (-0.5s cooldown, max 6x) — caps at -3s off the 6s
  cooldown, up to 2x roll frequency.
- **Weighted Die** (+1% high roll odds, max 30x) — improves average roll
  value. Estimated conservatively; the API doesn't expose the real odds
  table.
- **Dice Upgrade** (removes the "1" face from one die, uncapped but
  practically capped at once per die you own) — this is the highest-
  leverage upgrade once your multiplier climbs meaningfully above your
  floor, because every bust then costs more. Removing a die's 1
  multiplies your survival odds rather than just adding to them, and
  fully de-1'ing all your dice makes busting impossible, turning your
  multiplier into an uncapped climb. `advisor.py` models this with a
  Monte Carlo simulation (not a flat percentage like the others) that
  also weights each purchase by how close it gets you to full
  completion, since the last die fixed is worth far more than the first.
- **Unlock Skin** — cosmetic only, excluded from the value ranking.

`advisor.py` ranks all of these by estimated score-rate increase per
point spent, recalculated live off your current dice/multiplier/floor/
cooldown, so it naturally accounts for diminishing (or, for Dice
Upgrade, increasing-then-explosive) returns as you stack upgrades.

There's also a **group** project ("Build Foundation") needing a large
combined team score for a team-wide buff. A single player's rolls won't
move it alone, coordinate with your team if you want to push it over the
goal with `upgrades.py --contribute`.

## What this deliberately does not do

- Never uses another player's id, guessed or otherwise.
- `redeem.py` only ever submits codes you explicitly provide, it does not
  brute-force or guess promo codes.
- The auto-roller respects the server's cooldown (`nextRollTime`) instead
  of hammering the endpoint.
