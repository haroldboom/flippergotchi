# Flippergotchi 🐬

[![CI](https://github.com/haroldboom/flippergotchi/actions/workflows/ci.yml/badge.svg)](https://github.com/haroldboom/flippergotchi/actions/workflows/ci.yml)

A **Tamagotchi-style WiFi pet** for the [**Flipper One**](https://docs.flipper.net/one).
It's a Pwnagotchi at heart — it hunts WPA handshakes with the radio — but the
captures, walks, and AI personality are wired into a *pet you raise* instead of
a pwning machine.

> 📟 **This is for the Flipper One — NOT the Flipper Zero.** The Flipper One is
> the new, **unreleased** Rockchip RK3576 Arm-**Linux** handheld (Wi-Fi 6E +
> 6 TOPS NPU + FlipCTL UI) — a full Linux computer, not the Zero's
> microcontroller. The hardware isn't out yet, so today this runs entirely in
> **simulation** on any Linux box; the radio/GPS/Bluetooth/NPU hooks are
> clearly-marked TODOs that light up when the device ships.

- **WiFi APs are monsters you catch.** Each access point is a creature; net its
  handshake to add it to your **bestiary** (Pokémon-style) — *not* food.
- **Walking is the fitness core.** GPS movement → XP → levels → evolutions
  (egg → hatchling → … → legend), and your shark **forages food** (and, rarely,
  gear) as you walk — that's how the pet actually stays fed.
- **Crack & duel for loot.** Cracking a captured monster (at home) or duelling a
  rival Flippergotchi drops **equipment** you can equip.
- **The onboard AI is its voice.** The RK3576 NPU (or a CPU model, or canned
  phrases) narrates what the pet feels and what it just caught.
- **A cyberpunk pixel-art shark character** (AI-generated sprites) in an **old-school
  Pokémon-style 2D HUD**, at the Flipper One's native **256×144**. It **evolves**
  egg→legend and comes in 5 colour variants.

> **The economy at a glance:** walk → forage *food* (+ rare gear) · encounter →
> *catch* AP-monsters · crack at home → *loot* + score · duel rivals → *steal*
> gear & handshakes. APs are monsters; food comes from foraging.

### What it looks like

The game on the Flipper One's **256×144** screen — a retro Pokémon-style HUD
(HP / XP / food / energy + dialogue box) with the cyberpunk shark, scaled crisp
with nearest-neighbour. The sprite **swaps with the action** (Pwnagotchi-style):

![Flippergotchi gameplay](docs/demo.gif)

| Idle | Equipped gear shows on the character | Hungry |
|:---:|:---:|:---:|
| ![idle](docs/render-idle.png) | ![geared](docs/render-geared.png) | ![hungry](docs/render-hungry.png) |

**Action faces** — the character image changes by mood/action: idle · happy · chomp
(catching) · hungry · sleeping · hurt. **Every evolution stage** has the full set
(hatchling → legend), so the pet emotes at any age:

![action faces](docs/moods.png)

**Evolutions** — egg → hatchling → fingerling → juvenile → adult → alpha → legend:

![evolution stages](docs/evolutions.png)

**Colour variants** (`--variant` / `character_variant`): classic · blue · tiger · gold · reef

![colour variants](docs/variants.png)

…and your chosen colour **persists through every evolution** (e.g. blue, egg → legend):

![variant through evolution](docs/variant-evo.png)

**The monsters** — WiFi access points are catchable creatures whose **species is
the router's brand** (Netgear, TP-Link, Linksys, ASUS, Cisco, ISP…), with **WEP
& WPA1** as rare **legendaries**. Bluetooth devices are a friendlier
**mini-monster** tier. The BLE species come from the
real advert (device class + vendor): phones, wearables, audio, beacons,
computers, **trackers**, HID input, smart-home, medical. Scanning is a
*sighting*; an active **GATT enumerate** (`bettercap ble.enum` / `bleak`) is the
deeper **"tame"** — richer reward the more services the device exposes (gated +
audited like other active actions). A **tracker** (AirTag/Tile) that keeps
following you raises an **unwanted-tracker safety alert** and shows up as a rare
catch. Original cyberpunk pixel art throughout:

![bestiary — WiFi villains + BLE mini-monsters](docs/monsters.png)

**Encounters** render a classic Pokémon "A wild … appeared!" card — the monster
on its platform, a stat card (species / level / encryption / crack-difficulty),
and a Capture/Run menu:

![encounter screens](docs/encounter.png)

**Capturing** plays a net-gun animation that mirrors the real pentest flow: the
shark locks the target, fires **deauth** frames to kick clients, then listens for
the WPA **4-way handshake** until the capture timeout (a status HUD shows the
deauth count + capture progress). Two outcomes — handshake netted, or it times
out with no handshake:

| Handshake captured | No handshake (timed out) |
|:---:|:---:|
| ![capture success](docs/capture.gif) | ![capture failed](docs/capture-fail.gif) |

The listen window is **user-configurable** — `--capture-timeout <seconds>` (or
`capture_timeout` in config); the same value drives the real capture and is shown
on screen.

**PvP duel screen** — `duel <name>` renders a Pokémon-style 1v1: the rival
Flippergotchi (HP box, upper-left) faces your character (mirrored, lower-right)
with a live blow-by-blow in the dialogue box:

![duel battle screen](docs/battle.png)

**Equipment screen** — `gear` shows your character **wearing** the equipped
loadout (each piece composited at its slot, rarity-glowing) beside the five
slots, with your total **PvP power**:

![equipment screen](docs/equip.png)

> ℹ️ The character sprites are **AI-generated** (Google Gemini image models,
> `gemini-3-pro-image`) as original cyberpunk pixel art, then background-keyed to
> true alpha and packed into `flippergotchi/view/sprites/`. The device chassis is
> omitted (Flipper Devices' IP). Simulation renders — the hardware isn't out yet.

> ⚠️ **Authorized use only.** Capturing handshakes / deauthing is for networks you
> own or are explicitly permitted to test. Same rules as any WiFi audit tool.

> 🤖 **Built with AI assistance.** This is a passion project I designed and
> directed, but it was built hand-in-hand with an AI coding assistant — I
> couldn't have written it to this standard on my own. The ideas, design
> decisions, and direction are mine; much of the implementation was AI-assisted.
> I'm sharing it openly in that spirit. If AI-assisted code isn't for you, no
> hard feelings — feel free to give this one a miss. Otherwise, contributions
> and feedback are very welcome. 🙏

---

## Run it now (no hardware)

Everything runs on a normal Linux box in **simulation mode** — fake WiFi + GPS
events drive the real game loop, so you can watch the shark before a Flipper
One exists on your desk.

```bash
cd flippergotchi
pip install -e .                   # optional: installs the `flippergotchi` command
./run-dev.sh                       # live full-screen character, fast-forwarded
# or, with no install (pure stdlib):
python3 -m flippergotchi --simulate --plain --ticks 60   # log-only, no clear
```

While it runs it also writes a **256×144 LCD mock-up** to
`/tmp/flippergotchi/face.html` — open it in a browser to preview the on-device
FlipCTL view.

Run the tests:

```bash
python3 tests/test_mechanics.py    # or: python -m pytest
```

---

## Architecture

```
bettercap (radio)  ─┐
                    ├─► Agent ──► PetState (hunger/xp/level/health…)
gps (walking)      ─┘     │            │
                          │            ├─► AIService ──► [canned | cpu-llama | rkllm-npu]
                          │            │
                          └────────────┴─► view ──► [TUI text | FlipCTL HTML/LCD]
```

| Module | Role | Status |
|---|---|---|
| `core/wifi/` | native capture stack: monitor-mode mgmt, scan, hcxdumptool/scapy handshake+PMKID capture, `CaptureBackend` (auto: native→bettercap→sim) | sim ✅; hw path wired (needs on-device validation) |
| `core/handshake.py` | EAPOL 4-way / PMKID validation (pure-python pcap fallback) + `hcxpcapngtool` → hc22000 | ✅ done & tested |
| `core/authz.py` | deny-by-default scope guard for active RF actions + JSONL audit log | ✅ done & tested |
| `core/preflight.py` + `game/doctor.py` | `doctor` preflight: tools / privileges / iface / wordlist / scope | ✅ done & tested |
| `game/cracking.py` | hardened hashcat pipeline (PMKID/EAPOL, multi-wordlist + rules) | ✅ done & tested |
| `game/achievements.py` · `shop.py` · `gearsets.py` | badges · "scrap" currency + shop · gear-set bonuses | ✅ done & tested |
| `game/moves.py` | per-element PvP move sets + status effects | ✅ done & tested |
| `core/bettercap.py` | WiFi capture via bettercap REST | **sim works**; live wired (needs on-device validation) |
| `pet/gps.py` | GPS movement → walk distance | **sim works**; gpsd = TODO |
| `pet/mechanics.py` | hunger / xp / levels / evolution / mood | ✅ done & tested |
| `pet/state.py` | the savefile | ✅ |
| `ai/service.py` | event + mood → spoken line | ✅ (backend-pluggable) |
| `ai/canned.py` | phrase pools, zero deps | ✅ default |
| `ai/cpu_llama.py` | local GGUF via llama.cpp | works with a model |
| `ai/rkllm_npu.py` | NPU LLM (6 TOPS) | **stub** — waits on driver |
| `view/faces.py` | shark ASCII expressions (TUI) | ✅ |
| `view/tui.py` | dev terminal view | ✅ |
| `view/flipctl.py` | 256×144 Pokémon-style HUD + pixel sprite | ✅ render; plugin = TODO |
| `view/battle_screen.py` | Pokémon 1v1 PvP duel screen render | ✅ render |
| `view/equip_screen.py` | character-wearing-gear loadout screen render | ✅ render |
| `view/encounter_screen.py` | "A wild … appeared!" encounter card render | ✅ render |
| `view/capture_screen.py` | net-gun capture animation frames (aim→net→GOTCHA) | ✅ render |
| `view/monster_art.py` | species → enemy/mini-monster sprite lookup | ✅ done & tested |
| `view/sprites/` | AI-generated cyberpunk sprites (character + monsters) | ✅ |
| `game/analysis.py` | crack-difficulty heuristics (the analyst) | ✅ done & tested |
| `game/monsters.py` | AP/BLE → collectible monster + stats | ✅ |
| `game/bestiary.py` | your captured collection (savefile) | ✅ |
| `game/battle.py` | hashcat -m 22000 + rockyou → cloud fallback, auth-gated | sim ✅; hw path wired (needs on-device validation) |
| `game/cracking.py` (CloudCracker) | real wpa-sec/onlinehashcrack upload + result retrieval | ✅ done & tested (wpa-sec validated path) |
| `game/encounter.py` | detect → Capture/Run state machine | ✅ done & tested |
| `game/home.py` | "are we home?" gate for battling | ✅ |
| `game/ledger.py` | wins / losses / escalations database | ✅ done & tested |
| `game/duel.py` | Digimon-style PvP: turn-based moves + status effects + STAB | ✅ done & tested |
| `game/equipment.py` | gear: loot, equip, forfeit-on-loss | ✅ done & tested |
| `game/elements.py` | Spark/Tide/Gale/Aether matchup chart | ✅ done & tested |
| `game/quests.py` | daily quests + rewards | ✅ done & tested |
| `prefs.py` | persistent prefs (e.g. dismissed warning) | ✅ |
| `view/animations.py` | net-gun / flee ASCII animation frames | ✅ |
| `core/bluetooth.py` | BLE devices → mini-monsters | sim ✅; BlueZ = TODO |

## The RPG layer — a WiFi-pentest fitness game

It's also an [Orna](https://orna.guide)-style GPS RPG layered on the same data:

- **You level up by walking** (GPS = fitness/XP), same as the pet.
- **APs are monsters — species by the router's BRAND.** The vendor (from the
  BSSID OUI / SSID) picks the species: Netgear→Gnashgear, TP-Link→Mantalink,
  Linksys→Synksquid, ASUS→Asurpent, Cisco→Kragnet, an ISP→Telewyrm, unknown→
  Crypterion. Band = element, clients = minions.
- **WEP & WPA1 are rare LEGENDARIES** (Wepwraith / Wparchon). Legacy security is
  trivially broken, so they're a prized, easy catch — and they crack **on the
  fly** in the field (no trip home): WEP via **aircrack-ng** (IV attack, no
  wordlist), WPA1 via the handshake path. Still authorization-gated.
- **Bluetooth devices are smaller monsters** — see the BLE section above.
- **Battling = cracking.** WPA2 is the slow one: capture the handshake, then
  `hashcat -m 22000` + rockyou at home; if it survives and you allow it, escalate
  to a **cloud crack** (real wpa-sec upload; `cloud results` pulls keys back).
- **Only crackable networks are surfaced** (open / WEP / WPA / WPA2-PSK). WPA3,
  WPA2-Enterprise and OWE aren't wordlist-crackable, so they're not shown at all.

> 🔒 **Battles are authorization-gated.** Capturing/collecting is passive and
> always allowed, but *cracking* only runs against networks whose SSID/BSSID is
> in `home_networks` (your dojo) — or a one-off `--authorized`. Crack only what
> you own or are cleared to test.

### The encounter flow (Pokémon GO-style)

```
AP detected ─► POPUP "[A] Capture  [B] Run"
                 │
       ┌─────────┴─────────┐
   Capture                Run
       │                    │
  net-gun animation     flee animation
   ├─ caught  → bestiary (handshake = food for the pet)
   └─ escaped → broke free, no handshake
```

Capture success is about **radio** (clients present, signal strength) — not
encryption. *Battling* (cracking) is a separate, deliberate step you do **at home**:

```
game/encounter.py   detect → Capture/Run → caught/escaped/fled  (+ animations)
game/home.py        at_home(geofence OR home network in range) → battle unlocked
game/battle.py      hashcat+rockyou → cloud, gated to your dojo, with a warning
```

### CLI

```bash
python3 -m flippergotchi --simulate        # run: walk, encounter, capture, collect
python3 -m flippergotchi encounter         # demo one encounter (popup + animation)
python3 -m flippergotchi dex               # bestiary + your W/L/escalate record
python3 -m flippergotchi battle Linksys    # crack one (gated to home_networks)
python3 -m flippergotchi battle --all      # auto-battle every captured monster
python3 -m flippergotchi battle --all --dont-show-again   # ...and stop warning me
python3 -m flippergotchi quests            # today's daily quests + progress
python3 -m flippergotchi duel ByteSurf     # PvP duel (moves + element matchups)
python3 -m flippergotchi gear              # inventory / equip loadout
python3 -m flippergotchi doctor            # preflight: tools/iface/wordlist/scope
python3 -m flippergotchi scan              # passive AP discovery (no active actions)
python3 -m flippergotchi --dry-run capture AA:BB:..  # capture+validate, no deauth
python3 -m flippergotchi --capture-timeout 45 capture AA:BB:..   # longer listen window
python3 -m flippergotchi --dry-run battle MyAP --authorized   # crack path, no hashcat
python3 -m flippergotchi cloud                    # cloud status + queued captures
python3 -m flippergotchi cloud submit MyAP --authorized   # upload to wpa-sec
python3 -m flippergotchi cloud results            # pull recovered keys into the dex
python3 -m flippergotchi achievements      # badges unlocked + scrap balance
python3 -m flippergotchi shop              # browse; `shop buy <id>` to spend scrap
python3 -m flippergotchi --simulate --manual   # choose [A]Capture/[B]Run yourself
python3 -m flippergotchi --simulate --variant tiger   # pick your shark colour
```

- **Scrap economy**: cracking, catching, walking and winning duels earn **scrap**
  — spend it in the `shop` on food, energy/repair, monster lures, or a gear
  reroll token. **Achievements** unlock milestone badges (with small rewards).
- **Gear sets**: matching themed pieces grant a set bonus to **PvP power only**
  (never WiFi cracking — that stays deterministic from the network).

- **Daily quests** (`quests`): walk N km, catch N monsters, crack one, win a duel,
  forage snacks — completing one grants XP / handshakes / gear. Reroll each day.
- **Element type-advantage**: every fighter has an element (Spark/Tide/Gale/Aether);
  matchups tilt duel odds (`game/elements.py`).
- **Manual mode** (`--manual`): you press A/B per encounter instead of the auto-policy.
- **"You're home" prompt**: the run loop nudges you to `battle --all` when you
  arrive in your dojo with monsters ready.

- **Auto-battle** (`--all`) fights every captured, un-defeated WiFi monster one
  at a time and prints a lifetime **W / L / escalated** tally.
- The bestiary is keyed strictly by **BSSID**, so two different hidden networks
  never collapse into one and the same AP is never duplicated.
- Every battle is logged to `game/ledger.py` (**win** = cracked, **loss** =
  failed, **escalate** = uploaded to the cloud cracker).
- The crack **warning** has a *do-not-show-again* (`--dont-show-again`) that
  persists in `prefs.json`.

### PvP duels + equipment (Digimon-style)

When another Flippergotchi is detected advertising over **Bluetooth**, you can
challenge it:

```bash
python3 -m flippergotchi duel              # list nearby Flippergotchis
python3 -m flippergotchi duel ByteSurf     # challenge one
python3 -m flippergotchi gear              # your inventory + equipped loadout
python3 -m flippergotchi gear <item-id>    # toggle equip / unequip
```

- **Power** = level (dominant) + handshake pool + **equipped gear** + condition.
  Win chance comes from the power ratio, but upsets are always possible
  (clamped 8–92%), so a strong loadout matters but never guarantees a win.
- **Stakes:** the loser forfeits a slice of their **handshakes** *and* **a bit
  of gear** (weakest *unequipped* item first — equipped gear is protected).
- **Gear = findable pieces you slot on:** five slots — **helmet · eyepiece ·
  amulet · weapon · fin** — each item rolls a PvP stat (ATK / DEF / LUCK) and a
  rarity (common→legendary). Loot them from captures and walks; only *equipped*
  pieces count.
- **Distinct art + effects per rarity:** every slot has 5 looks (common grey → legendary radiant gold). Worn pieces glow by rarity (rare cyan · epic purple · **legendary gold, with a live pulse**).
- **Gear only matters in PvP.** It does **not** help against WiFi monsters —
  cracking is a deterministic wordlist attack, not a stat check.

The **analyst** runs automatically on every capture (difficulty + suggested
attack + the exact hashcat command); on the `cpu`/`npu` AI backend it's narrated
by the local LLM, on `canned` it's the deterministic heuristic.

## AI backends

Set `ai_backend` in config (or leave default):

- **`canned`** — phrase pools, no dependencies. The default; always available.
- **`cpu`** — a small GGUF (e.g. Qwen2.5-1.5B-Instruct) via `llama-cpp-python`.
  Runs today on the RK3576 A72 cores. Set `ai_model_path`. **This is the
  launch-day path.**
- **`npu`** — Rockchip **RKLLM** runtime on the 6 TOPS NPU. *Stubbed* until the
  mainline RK3576 NPU "rocket" driver ships
  ([tracking issue #55](https://github.com/flipperdevices/flipperone-linux-build-scripts/issues/55)).
  `build_backend()` falls back automatically, so nothing breaks before then.

The whole point of the abstraction: **ship on `canned`/`cpu` now, flip to `npu`
later with no redesign.**

## The WiFi penetration stack

The radio side is built to be **rock-solid and safe**: pluggable backends, real
handshake *validation* (not just "we wrote a file"), a hard authorization gate on
every active action, and a `doctor` that tells you exactly what's missing.

```
core/wifi/monitor.py    monitor-mode iface mgmt: detect MT7921, airmon-ng / iw,
                        rfkill, regdomain, channel set + hop plans, capabilities()
core/wifi/scan.py       passive AP/client discovery (iw scan / airodump CSV)
core/wifi/capture.py    handshake + PMKID capture: hcxdumptool → scapy fallback,
                        AUTHORIZED targeted deauth only
core/wifi/backends.py   CaptureBackend abstraction; make_backend() auto-selects
                        native → bettercap → sim (override: cfg.capture_backend)
core/handshake.py       validate EAPOL 4-way (M1–M4) / PMKID before cracking —
                        pure-python pcap/pcapng parser, no external tool needed
game/cracking.py        hashcat -m 22000 (PMKID/EAPOL), multi-wordlist + rules,
                        structured CrackResult; deterministic sim fallback
core/authz.py           in_scope() + Authorizer: deny-by-default, allowlist file,
                        JSONL audit log of every deauth/capture/crack
```

**Authorization model.** Passive scanning is always fine. *Active* actions
(deauth, capture, crack) are refused unless the target matches `home_networks`
**or** your `~/.flippergotchi/allowlist.txt` — deny-by-default, and every attempt
(allowed or denied) is appended to `~/.flippergotchi/audit.log`. Only crack
networks you own or are authorized to test.

**Preflight.** `python3 -m flippergotchi doctor` reports tools
(`hcxdumptool`/`hcxpcapngtool`/`hashcat`/`iw`/…), privileges (root / CAP_NET_ADMIN),
the monitor interface, the wordlist, and your scope — then a plain-English
"you can: [passive scan] [capture] [crack]" summary with fix-it hints.

**Dry-run (validate on hardware safely).** `--dry-run` drives the *real* paths —
monitor mode, passive scan, capture-listen, handshake validation, and hashcat
command construction — but suppresses the two irreversible/expensive actions:
**deauth injection** and **actually running hashcat**. Bring up a monitor-mode
dongle and walk the stack end-to-end without attacking anything:

```bash
python3 -m flippergotchi doctor                         # 1. is the stack ready?
python3 -m flippergotchi scan                           # 2. passive: do I see APs?
python3 -m flippergotchi --dry-run capture <bssid>      # 3. capture+validate (no deauth)
python3 -m flippergotchi --dry-run battle <name> --authorized   # 4. shows the exact
                                                        #    hashcat cmd it WOULD run
```

`capture` prints whether the resulting file holds a PMKID / complete 4-way; the
dry-run `battle` validates the capture and prints `would run: hashcat -m 22000 …`
without executing it. Drop `--dry-run` (with proper authorization) to go live.

## Porting to real hardware (when the Flipper One arrives)

1. **Capture:** install `hcxdumptool`/`hcxpcapngtool`/`hashcat`, set
   `simulate = false`, run `doctor` until it's green, add your AP to
   `home_networks`/allowlist, point `interface` at the MT7921 monitor iface.
   `make_backend()` then picks the native stack automatically (or set
   `capture_backend = "bettercap"` to drive a running bettercap REST session).
   On a live backend the encounter loop **actually runs** the deauth + handshake
   capture (`backend.capture_handshake`, bounded by `capture_timeout`) and the
   real radio result decides catch vs. no-handshake — the capture file is kept on
   the monster for later cracking/upload. In `--simulate` this is skipped and the
   outcome stays a synthetic roll, so nothing changes without hardware.
2. **Walking:** implement `GpsReader._gpsd_step()` against `gpsd`. Set
   `gps_mode = "gpsd"`.
3. **Face:** wrap `view/flipctl.py`'s markup in a real FlipCTL plugin and map the
   D-pad / soft-buttons (feed, pause, sleep, stats) to actions.
4. **AI:** convert a sub-3B model to `.rkllm`, finish `ai/rkllm_npu.py`, set
   `ai_backend = "npu"`.

The game logic in `pet/` and `agent.py` does **not** change between sim and
hardware — that's the design. Every hardware path is marked
`NEEDS ON-HARDWARE VALIDATION` and degrades to sim/None rather than crashing.

## Roadmap ideas

- ~~LLM "analyst" mode~~ ✅ done (`game/analysis.py` + `AIService.analyze`).
- ~~APs as catchable monsters; BLE as mini-monsters; hashcat/cloud battles~~ ✅
  scaffolded (`game/`).
- ~~Type/element advantages; daily quests; manual capture mode~~ ✅ done.
- ~~Native capture stack (monitor-mode, scan, hcxdumptool/scapy capture, backend
  abstraction)~~ ✅ done (`core/wifi/`).
- ~~Handshake/PMKID validation + `hcxpcapngtool`→hashcat conversion~~ ✅ done
  (`core/handshake.py`, `game/cracking.py`).
- ~~Authorization scope guard + audit log + `doctor` preflight~~ ✅ done
  (`core/authz.py`, `game/doctor.py`).
- ~~Progression: achievements, scrap economy + shop, gear sets~~ ✅ done.
- ~~PvP moves + status effects~~ ✅ done (`game/moves.py`, `game/duel.py`).
- ~~Cloud crack: real wpa-sec/onlinehashcrack upload + result retrieval~~ ✅ done
  (`game/cracking.py` `CloudCracker`, `cloud submit` / `cloud results`).
- Real-hardware paths are **implemented but unvalidated** (need a device):
  - `core/wifi/*` native capture · `core/bettercap.py` live REST client
  - `pet/gps.py` gpsd reader · `core/bluetooth.py` BLE scan via optional `bleak`
  - still TODO: FlipCTL device plugin, RKLLM NPU backend.
- Step counter via the device IMU (true pedometer) alongside GPS distance.
- Reinforcement-learning channel hopper (classic Pwnagotchi A2C) as an optional
  capture optimizer — CPU, independent of the LLM.
- Trade/share your bestiary; co-op "raids" on tough APs over BLE.

## License

[MIT](LICENSE) © 2026 haroldboom. Built with AI assistance (see the note at the
top). Use the WiFi/Bluetooth capabilities only on networks and devices you own
or are authorized to test.

## Trademarks & affiliation

Flippergotchi is an **independent, unofficial fan project**. The character art is
original art; its colour variants are *inspired by* classic '90s shark-toon
characters but use generic descriptive names and original artwork — those
characters are trademarks of their respective owners and aren't used here. It is
also **not affiliated with, endorsed by, or sponsored by Flipper Devices Inc.** "Flipper",
"Flipper One", and the Flipper dolphin are trademarks of Flipper Devices Inc.,
used here only **nominatively** to indicate the target hardware. **No official
Flipper Devices artwork, renders, logos, or insignia are included in this
repository** — the device mock-up is original art. Flipper Devices' brand policy
requires written authorization to use their marks/assets, so if you fork or
redistribute this, keep it clearly unofficial. The MIT license covers this
project's own code and art only.
