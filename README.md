# Flippergotchi 🐬

A **Tamagotchi-style WiFi pet** for the [Flipper One](https://docs.flipper.net/one).
It's a Pwnagotchi at heart — it hunts WPA handshakes with the radio — but the
captures, walks, and AI personality are wired into a *pet you raise* instead of
a pwning machine.

- **Handshakes are food.** Every WPA handshake / PMKID the radio captures feeds
  the pet and lowers its hunger. Full handshakes are a meal; PMKIDs are snacks.
- **Walking levels you up.** GPS movement is exercise → XP → levels → evolutions
  (egg → hatchling → … → legend).
- **The onboard AI is its voice.** The RK3576 NPU (or a CPU model, or canned
  phrases) narrates what the pet feels and what it just caught.
- **The face is the Flipper dolphin**, rendered to the 256×144 LCD via FlipCTL.

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
events drive the real game loop, so you can watch the dolphin before a Flipper
One exists on your desk.

```bash
cd flippergotchi
./run-dev.sh                       # live full-screen dolphin, fast-forwarded
# or:
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
                          └────────────┴─► view ──► [TUI dolphin | FlipCTL HTML/LCD]
```

| Module | Role | Status |
|---|---|---|
| `core/bettercap.py` | WiFi capture → food events | **sim works**; live = TODO (REST/ws) |
| `pet/gps.py` | GPS movement → walk distance | **sim works**; gpsd = TODO |
| `pet/mechanics.py` | hunger / xp / levels / evolution / mood | ✅ done & tested |
| `pet/state.py` | the savefile | ✅ |
| `ai/service.py` | event + mood → spoken line | ✅ (backend-pluggable) |
| `ai/canned.py` | phrase pools, zero deps | ✅ default |
| `ai/cpu_llama.py` | local GGUF via llama.cpp | works with a model |
| `ai/rkllm_npu.py` | NPU LLM (6 TOPS) | **stub** — waits on driver |
| `view/faces.py` | dolphin ASCII expressions | ✅ |
| `view/tui.py` | dev terminal view | ✅ |
| `view/flipctl.py` | 256×144 HTML → LCD | mock done; plugin wiring = TODO |
| `game/analysis.py` | crack-difficulty heuristics (the analyst) | ✅ done & tested |
| `game/monsters.py` | AP/BLE → collectible monster + stats | ✅ |
| `game/bestiary.py` | your captured collection (savefile) | ✅ |
| `game/battle.py` | hashcat+rockyou → cloud fallback, auth-gated | sim ✅; hw cmds = TODO |
| `game/encounter.py` | detect → Capture/Run state machine | ✅ done & tested |
| `game/home.py` | "are we home?" gate for battling | ✅ |
| `game/ledger.py` | wins / losses / escalations database | ✅ done & tested |
| `game/duel.py` | Digimon-style PvP between Flippergotchis | ✅ done & tested |
| `game/equipment.py` | gear: loot, equip, forfeit-on-loss | ✅ done & tested |
| `prefs.py` | persistent prefs (e.g. dismissed warning) | ✅ |
| `view/animations.py` | net-gun / flee ASCII animation frames | ✅ |
| `core/bluetooth.py` | BLE devices → mini-monsters | sim ✅; BlueZ = TODO |

## The RPG layer — a WiFi-pentest fitness game

It's also an [Orna](https://orna.guide)-style GPS RPG layered on the same data:

- **You level up by walking** (GPS = fitness/XP), same as the pet.
- **APs are monsters.** Encryption = difficulty/defense, vendor = species, band =
  element, clients = minions. *Spotting* one logs it; *capturing* the handshake
  adds it to your **bestiary** ready to battle.
- **Bluetooth devices are smaller monsters** — collected/"tamed" by scanning
  (no handshake to crack), a distinct lighter tier.
- **Battling = cracking.** `hashcat -m 22000` + rockyou locally; if a tough
  target survives and you allow it, escalate to a **cloud crack**
  (`wpa-sec` or `onlinehashcrack` — two separate services).
- **WPA3/SAE & WPA2-Enterprise are "immune"** to wordlists — correctly modelled
  as bosses you can't beat this way.

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
encryption — so you can net a WPA3 handshake; you just can't crack it later.
*Battling* (cracking) is a separate, deliberate step you do **at home**:

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
```

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
- **Gear** drops from captures (`loot_chance`) and is won in duels. Five slots
  (antenna / battery / cpu / charm / hull), five rarities (common→legendary);
  only equipped items count toward your power.

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

## Porting to real hardware (when the Flipper One arrives)

1. **Capture:** implement `BettercapClient.start()/poll()` against bettercap's
   REST + websocket API on the MT7921 monitor interface (`mon0`). Set
   `simulate = false`.
2. **Walking:** implement `GpsReader._gpsd_step()` against `gpsd`. Set
   `gps_mode = "gpsd"`.
3. **Face:** wrap `view/flipctl.py`'s markup in a real FlipCTL plugin and map the
   D-pad / soft-buttons (feed, pause, sleep, stats) to actions.
4. **AI:** convert a sub-3B model to `.rkllm`, finish `ai/rkllm_npu.py`, set
   `ai_backend = "npu"`.

The game logic in `pet/` and `agent.py` does **not** change between sim and
hardware — that's the design.

## Roadmap ideas

- ~~LLM "analyst" mode~~ ✅ done (`game/analysis.py` + `AIService.analyze`).
- ~~APs as catchable monsters; BLE as mini-monsters; hashcat/cloud battles~~ ✅
  scaffolded (`game/`).
- Real-hardware wiring: bettercap live capture, gpsd steps, BlueZ scan,
  hcxpcapngtool→hashcat, wpa-sec/onlinehashcrack uploads (all marked TODO).
- Step counter via the device IMU (true pedometer) alongside GPS distance.
- Type/element advantages in battle; daily quests ("walk 2 km", "catch a WPA3").
- Reinforcement-learning channel hopper (classic Pwnagotchi A2C) as an optional
  capture optimizer — CPU, independent of the LLM.
- Trade/share your bestiary; co-op "raids" on tough APs over BLE.
