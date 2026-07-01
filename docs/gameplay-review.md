# Flippergotchi — Gameplay & Cohesion Review

*Five parallel design reviews (core loop / pet fantasy, progression & retention,
economy & balance, combat depth, cohesion & theme). Each read the real code and
tunables and ran the `--simulate` build to feel the loop. Recommendations only —
no code changed. File/line references are to the current tree.*

---

## Verdict

**It is functional but not yet fun — a beautifully-engineered screensaver, not yet
a game. The good news, echoed by four of the five reviewers independently: the fix
is mostly *tuning and connecting systems that already exist*, not a rewrite.**

Every system is built, wired, tested, and on-theme. But played end to end, three
things stop it being fun:

1. **It runs itself with no scarcity** — in auto mode the player makes zero
   moment-to-moment decisions and rewards arrive every tick, so nothing lands.
2. **A large RPG/combat/gear/element cluster is disconnected from the pet's life** —
   the automatic loop never touches it, and its depth never reaches the player.
3. **The pet-care fantasy is emotionally inert** — hunger can't fail, normal-mode
   death is impossible, and hardcore death churns past in the log-spam.

What's genuinely good and must be preserved: the **fiction** ("APs are monsters,
walking forages food, WEP/WPA are legendaries" — a clever Pwnagotchi reframe); the
**action-interlock** (one walk advances a daily + weekly + chain + achievement at
once); the **consent/authorization discipline**; the **persistent species identity**
(`character_variant` egg→legend); and a genuinely capable but **unused duel engine**.

---

## The five biggest problems (ranked by cross-agent convergence × impact)

### 1. The RPG/combat/gear/element/sets cluster is an orphan island — *flagged by 4 of 5*
The auto-loop never initiates a duel; it only prints "duel it with `duel X`"
(`agent.py`). So an entire, well-built stack — `duel.py`, `moves.py`, `elements.py`,
`gearsets.py`, and the PvP half of `equipment.py`/`titles` — hangs off a manual
command the pet's daily life never triggers. Worse, the depth is *disconnected even
inside combat*:
- **Every fight is a zero-input RNG roll.** WiFi crack is literally
  `random() < 1 - defense/100` (`cracking.py:292`); BLE battle is a hardcoded odds
  table (`blebattle.py:119`); duels auto-pick moves the player never sees
  (`moves.py:107`). Four "combat systems" are really one auto-resolver in four costumes.
- **The player's element is frozen at `Aether` forever** — nothing in the codebase
  ever sets `PetState.element` (`pet/state.py:30`), yet element is the single biggest
  win-rate lever (87% vs 14% on a matchup swing). The elegant type chart flips a coin
  the player can't influence.
- **Gear is a decorative scalar.** `atk`/`def`/`luck` and all of `gearsets.py` set
  bonuses are shown in the UI but **never read by the resolver**; `pvp_power()` is
  called only in tests. Completing a gear set does nothing in a fight.
- **Gear is inert on a solo device anyway** — it only matters in PvP duels, which need
  a nearby peer, so on a single device looted gear never affects any challenge.

**Two forks, pick one:** (a) **connect it** — auto-resolve occasional duels against
detected peers, auto-equip best-in-slot, and wire gear stats + element + set bonuses
into the resolver (the engine is already written; this is ~1–2 days and is the single
change that most turns "pile of features" into "one game"); or (b) **cut it down** —
accept PvP is a manual side-mode and remove the dead surface (`gearsets.py`, PvP stat
tags) so the game stops advertising depth it doesn't deliver.

### 2. No scarcity — the loop is a firehose that plays itself — *core loop*
Sim emits an AP ~35%/tick and captures ~85% of them, so nearly every tick logs a
catch/forage/recon (`bettercap.py:277`, `encounter.py:26,76`). A reward you get every
second is wallpaper. There is no "one more minute" hook because nothing is ever
*almost* done **in view** — no "next evolution in 2 catches," no "shiny nearby." And
the encounter itself has no decision: `--manual` adds a binary A/B prompt you almost
always answer "capture," which is prompt-fatigue, not agency.

### 3. The pet-care fantasy is emotionally inert — *core loop + economy*
The one thing meant to make you *care* has no weight:
- **Hunger cannot fail in auto play.** Foraging out-produces hunger decay by ~150×
  while walking (`forage_food_per_m=0.06` vs `hunger_per_hour=50`), and the pet
  auto-eats at `hunger≥55`, so it feeds itself before hunger ever bites. Hunger,
  happiness (a derived shadow of hunger), and satiety (invisible) are decorative meters.
- **Normal-mode death is impossible** — health is floored at 1 (`mechanics.py:101`);
  `is_dead` is hardcore-only. For the ~99% who don't opt into permadeath, neglect is
  consequence-free.
- **Hardcore death churns past in spam** — "ABOUT TO DIE" and death land ~2 ticks
  apart (no runway), the death is one log line between "caught NETGEAR!" lines, and
  `reborn` instantly respawns keeping the whole collection. No pause, no gravestone,
  no memorial.
- **Energy/sleep is dead code** — nothing ever sets `asleep=True`, so the tired/sleeping
  states are unreachable and energy is a one-way drain with no restore path.

### 4. The economy has no sink; scrap inflates to irrelevance — *flagged by 3 of 5*
A sim session earned **~1300–2200 scrap** passively while the dearest shop item costs
**220** — the shop is never a decision. Compounding it:
- **Auto-cracking OPEN networks is the degenerate strategy**: 120 scrap + a guaranteed
  gear roll for *zero* effort (`agent.py` OPEN branch), equal to a real WEP/WPA crack
  and 8× a catch.
- **`xp_per_snack` makes leveling "time-on-foot"** (~950 XP/hr from eating alone),
  diluting catching as the progression driver.
- BLE recon may **re-pay its reward on every re-sighting** (a passive faucet).

### 5. The "collection" isn't a collection, and the payoffs are front-loaded — *flagged by 2 of 5*
- The **dex is a BSSID packet-log, not a species dex** — it shows the same SSID/species
  many times (each a technically-unique BSSID), so your prized collection reads as spam.
  There is no finite "X/19 species" counter and no completion reward — the most natural
  goal in a creature-collector is absent.
- **Dopamine is violently front-loaded**: a ~3-hour session already saw 15/19 species,
  the "rare" shiny badge, silver catch-50, and every title within reach. `SHINY_ODDS`
  per-AP means a shiny appears day 1.
- **A dead evolution middle**: juvenile (L8) → alpha (L25) is a ~4-month, ~180k-XP
  plateau with no evolution or stage feedback; legend is ~1.3 years out. Only 5 stages
  exist and 2 are spent on day 1.
- **No endgame**: badges/species/titles exhausted in ~1–2 days; streaks go inert after
  the day-7 badge; chains are just 9 lifetime steps. Week-2 has nothing to return for.

### Also flagged
- **The AI voice narrates only ~40% of the pet's life** — it speaks on catch/feed/level/
  evolve/mood but is silent on quest-clear, badge unlock, crack success, shiny, and
  starvation, and never references the pet's own history. The events already flow through
  `_quest`/`_achievements`/`_field_battle`; they just don't call `speak()`.
- **BLE tone clashes with the game's ethic** — the cute-pet, per-AP-consent framing
  breaks in `blebattle.py`, which "owns" real devices (Fitbit, glucose monitor, hearing
  aid, AirTag) and exfiltrates health/location/audio. It's the least pet-like, most
  surveillance-invasive system, dressed as the friendliest.

---

## Recommendations

### Quick wins — tuning + small UX, highest fun-per-hour (each ~hours)
| # | Change | Where |
|---|---|---|
| 1 | **Throttle the firehose** — sim AP spawn 0.35→~0.12, BLE 0.15→~0.05, so catches feel earned | `bettercap.py:277`, `bluetooth.py` |
| 2 | **Make hunger bite** — `forage_food_per_m` 0.06→~0.01 and/or raise `forage_auto_eat_hunger` 55→~80 so `feed`/larder matter | `config.py` |
| 3 | **Fix the degenerate OPEN-crack** — pay catch-tier (~15–25), drop the guaranteed loot; reserve 120+loot for real WEP/WPA | `agent.py` OPEN branch |
| 4 | **Add scrap sinks / throttle payouts** — ~3–5× shop prices, `SCRAP_PER_CATCH` 15→~8 | `shop.py` |
| 5 | **De-dupe the dex into a species collection** — one card per species w/ count + best level + shiny, keep BSSID keying under the hood | `bestiary.py`, `commands.py` (dex) |
| 6 | **Give the pet a voice at every payoff** — `speak()` on quest-clear, badge, crack, shiny, starvation; widen canned pools to 6–8 lines + self-reference | `ai/canned.py`, `agent.py` |
| 7 | **Wire the combat depth that's already built** — seed duel atk/def from gear, use `pvp_power()` (set bonuses), let the player choose/earn an element, show the matchup before a duel | `duel.py`, `commands.py`, `pet/state.py` |
| 8 | **Give hardcore death weight** — runway (grace ticks independent of `time_scale`), then pause + render a gravestone/epitaph before `reborn`, gated on a keypress | `agent.py`, `mechanics.py` |
| 9 | **Onboarding** — first `--reset`: name prompt, one hatch beat, 2 lines of "walk→forage, catch, feed"; suppress the hashcat/analyst jargon for the first ~5 catches | `__main__.py`, `agent.py` |
| 10 | **`xp_per_snack` 2.0→~0.5**, gate BLE recon reward to first interrogation, wire/cut energy-sleep | `config.py`, `agent.py` |

### Bigger design changes
- **Pull duels/gear into the auto-loop, or shrink the cluster** (problem 1's fork (a) is the single biggest coherence win).
- **Make the encounter a real decision** — a scarce "net charge" resource that regenerates by walking, so capturing is a risk/reward beat (spend now vs save for a shiny/legendary). Biggest "screensaver → game" lever.
- **Add mid/late evolution stages + retune the curve** — 2 stages in the L8–25 hole and `level_exp` ~1.6→~1.35–1.4 so an evolution lands roughly weekly through month 1.
- **A real endgame** — paragon/prestige past L40, a rotating weekly challenge + seasonal title, a finite named-boss hunt, or a duel ladder/rank.
- **Soft stakes for normal mode** — neglect costs something short of permadeath (sickness, a sulking pet that won't forage, stalled evolution, broken streak) so care matters for the 99%.
- **Make the pet a bond, not a meter** — per-pet preferences (favorite food/species), reactions to *your* milestones, and a "life so far" line the pet narrates about its own run (feeds off `profile`+`ledger`+`bestiary`).
- **A "one more minute" hook in the loop view** — always show one near-term goal ("next evolution in 2 catches", "larder 18/20 → feast", "✨ shiny nearby").

### Explicit cuts (the 20%, for cohesion)
- `gearsets.py` set bonuses — invisible until gear is in the loop.
- `title` as a standalone wearable/command — fold into the badge wall as flavor.
- Shop food SKUs (`ration`/`feast`/`energy_snack`) — the forage loop already feeds the pet.
- `reroll_token` — only meaningful if gear matters; keep it with the gear cluster or cut it.
- **Reconcile or re-skin the BLE surveillance flavor** to match the consent/pet ethic.

---

## The three cheapest moves that raise fun *and* coherence at once
Where the reviewers most agreed on value-per-effort:
1. **Render the dex as a species collection** (turns spam back into a Pokédex).
2. **Give the pet a voice at every progression payoff** (makes it feel like one life, not parallel counters).
3. **Connect the orphan combat/gear cluster to the loop — or cut it** (resolves the single biggest cohesion problem).

## Convergence map

| Finding | core loop | progression | economy | combat | cohesion |
|---|:-:|:-:|:-:|:-:|:-:|
| Orphan combat/gear/element cluster | | ● | ● | ● | ● |
| No scrap sink / inflation | | ● | ● | | ● |
| Pet-care emotionally inert | ● | | ● | | |
| Collection isn't a real dex | | ● | | | ● |
| Front-loaded / no endgame | ● | ● | | | |
| AI voice narrates only part of the life | ● | | | | ● |
| No scarcity / firehose / no agency | ● | | | ● | |

---

## Holistic take

The engineering is not the problem — the systems are well-built, tested, and on-theme.
The problem is that they don't yet add up to a *game you play* or a *pet you love*: the
loop runs itself, the depth is disconnected, and the care meters can't fail. Because the
depth is already written, the path to "fun but functional" is short: **add scarcity so
choices matter, connect the orphaned systems to the pet's daily life (or cut them), and
give the collection and the pet's death real weight.** Do the ten quick wins and the pet
stops being an impressive demo and starts being one shark you're actually raising.
