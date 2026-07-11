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

All scripts accept `--user-id`.

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

## Strategy notes (from API inspection)

Each roll: N dice (upgradeable) summed, multiplied by your multiplier,
e.g. sum=6, multiplier=2 -> +12 score. Cooldown starts at 6000ms.

Solo projects let you spend your own score as "gold" for permanent
upgrades:

- **Level Up!** (+1 Die, repeatable up to 50x) — more dice = more score
  per roll, compounds well.
- **Skill Up!** (+1 Multiplier, uncapped repeats) — direct multiplier on
  every roll, very strong long-term.
- **Fast Hands** (-0.5s cooldown, max 6x) — caps at -3s off the 6s
  cooldown, up to 2x roll frequency. High value once affordable.
- **Weighted Die** (+1% high roll odds, max 30x) — improves average roll
  value.
- **Unlock Skin** — cosmetic only, excluded from the value ranking.

`advisor.py` ranks these by estimated score-rate increase per point
spent, recalculated live off your current dice/multiplier/cooldown so it
naturally accounts for diminishing returns as you stack upgrades.

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
