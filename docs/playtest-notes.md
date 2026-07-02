# Playtest pass — tuning validation & changes

*Empirical pass: an instrumented harness drove the real `Agent` loop headless and
Monte-Carlo'd the combat modules to measure the post-tuning constants against the
design targets in `docs/gameplay-review.md`. Measurements below are per **game-hour**
of active play (1 tick == 1 s at `tick_interval=1`; decay uses per-hour rates scaled
by `dt*time_scale`). Note: in `--simulate` the encounter RATE is set by
`SIM_AP_SPAWN_CHANCE` (a dev knob), so per-hour scrap/XP/catch totals are
sim-inflated; the environment-independent results (care timing, ratios, combat
odds) are what transfer to real hardware.*

## Changes applied this pass

1. **Auto-duel frequency + fair matchmaking** (`agent.py::_maybe_duel`). The old
   throttle (cooldown 12 ticks, 15%/tick) fired **~140 duels/game-hour** — log spam
   and a scrap firehose (~8k scrap/hr from duels alone). Now: cooldown **120**,
   chance **0.05**, and it only challenges a peer whose estimated `win_chance` is in
   a **[0.2, 0.85]** band (tunable via `auto_duel_min_odds`/`max_odds`). Re-measured:
   **~17 duel-wins/game-hour** — an occasional, competitive payoff, not the heartbeat.

2. **Combat upset floor — R1** (`game/duel.py`, new `UPSET_FLOOR = 0.05`). Duels
   were **0%/100% locks** at any real gap: a +30 gear-power edge was a ~95% win, a
   full-vs-no gear set was a flat **100%/0%**, because equipped stats double-dipped
   (both the HP pool *and* the per-hit multipliers) and a 30-turn attrition fight
   averages out variance. A read-only Monte-Carlo pass confirmed **no constant
   retune can remove the lock** — it only moves where it lands. Fix: the winner is
   now **rolled from the final HP share, clamped to [0.05, 0.95]** (with a
   "claws back" narration when the roll upsets the HP state). Measured before→after:

   | scenario | before | after |
   |---|---|---|
   | mirror (even) | .498 | .455 |
   | vs +60 gear peer | **.000** | .042 |
   | vs +150 gear peer | .000 | .052 |
   | vs +10 level peer | .022 | .067 |
   | element advantage | .906 | .871 |
   | element disadvantage | .052 | .092 |

   Favorites stay favored and gear/element remain real levers, but an underdog
   always has a fighting chance. All combat-wiring tests still pass (their bounds
   are directional, not exact).

## Measured healthy — left as-is

- **Neglect → sick** (stationary, normal mode): pet falls sick at **~7.3 game-hours**
  of neglect (hunger crosses 85 at ~1.3 h, then `sick_onset_hours=6`), and hand-feeding
  recovers it. "Leave it overnight and it's sick, feed it and it's fine" — on target.
  Normal mode **never dies** (health floored) — confirmed over 96 h of neglect.
- **Hardcore death runway**: from entering "faint" to death is **~5 game-hours** of
  escalating warnings — plenty of runway (was a cliff pre-tuning). Grace is in ticks,
  so the player always sees several warning frames.
- **Cracking curve** (`p = 1 − defense/100`, clamped .02–.97): open .97 → WEP .90 →
  WPA .66 → WPA2 .46 → secure-BLE .02. WPA2 near a coin-flip, legacy reliable, phones
  near-immune — a clean difficulty gradient. No change.
- **Evolution curve** (`level_exp=1.4`): cumulative XP to legend ~339k (vs ~653k
  pre-tuning) — reachable in weeks, not a year, with a mid-game evolution roughly
  weekly. Sim fast-forwards it (firehose), but the curve shape is right.

## Recommended follow-ups (measured, deliberately NOT changed this pass)

- **Combat R2/R3 — widen the "choices matter" band + make LUCK viable.** Even with the
  upset floor, gear/level differences snap toward the caps quickly and LUCK loses
  ~88% at equal budget (a trap stat / dead gear-set). Recommended: `ATK_STAT_SCALE`/
  `DEF_STAT_SCALE` 0.010→~0.006, `_hp_from_power` slope 1.2→~0.8, `LUCK_CRIT_SCALE`
  0.005→~0.008, `LUCK_CRIT_CAP` 0.35→~0.45. This is a **rebalance** — it shifts the
  numbers the `test_combat_wiring` suite pins, so it needs those thresholds re-tuned
  in the same change. Left for a focused combat-balance pass.
- **Displayed duel odds (R4).** `cmd_duel` shows `win_chance()` (a power-ratio
  estimate) which understates the favorite vs the actual resolver; now that R1 also
  clamps outcomes to [0.05, 0.95], the two are closer, but a perfectly-aligned display
  would derive from the same HP-share model.
- **Scrap sinks may want to scale.** Even after the duel fix, sim scrap/hr is high —
  but that's driven by the sim encounter rate, not a config imbalance; the real-hardware
  earn rate (environment-limited) is unknown. Revisit sink pricing once there's a real
  capture-rate signal, rather than tuning against the dev simulator.
- **Hunger is pinned near 0 while actively walking** (the larder fills, then overflow
  auto-eats). Thematically fine — a walking pet is a fed pet, and the stakes live in
  neglect (which now works) — but if you want the larder to be a buffer you actively
  draw down, trim `forage_food_per_m` further (0.01→~0.006) so a walking pet trends
  only slightly net-positive on food.
