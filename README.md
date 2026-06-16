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

- LLM "analyst" mode: explain each capture (SSID pattern → crack difficulty,
  suggested `hashcat -m 22000 …`).
- Sleep cycle tied to time-of-day; "treats" for new/rare networks.
- Reinforcement-learning channel hopper (the classic Pwnagotchi A2C brain) as an
  optional capture optimizer — runs on CPU, independent of the LLM.
- Save/share your dolphin's stats; multi-pet "pack" over BLE.
