# Flippergotchi → Flipper One: Implementation Review & Roadmap

*Read-only codebase review by six parallel subagents (WiFi/radio, BLE/GPS, AI/NPU,
UI/display, packaging/deploy, and hardware/SDK research), 2026-07-02. Recommendations
only — no code was changed. Every hardware claim below is cited to a source.*

---

## TL;DR

The project is in **much better shape than "needs a rewrite."** Its core hardware bets
are, surprisingly, mostly **right**, and the backend abstraction seam (`CaptureBackend`,
`AIBackend`, `GpsReader`, `BluetoothScanner`, all auto-selecting `sim → real`) is the
strongest part of the codebase — hardware backends genuinely drop in without touching
game logic.

The work that remains is **not** in the game or the abstractions. It is at the two edges:

1. **Safety enforcement** — the "deliberate, consent-gated capture" guarantee the project
   advertises is **not actually enforced on the default (bettercap) path**. This is the
   most important thing to fix and it is fixable in ~1 day.
2. **The device edges don't exist yet** — there is no on-device UI/input layer, no deploy
   story, and two mechanics (walking, NPU voice) depend on things the hardware either
   lacks (GPS) or can't run yet (NPU driver not mainlined).

---

## Hardware reality check (verified)

Flipper One was **announced May 21 2026, is not shipping**, and dev units are expected
"no earlier than summer 2026." So today the app can only be validated in simulation and
against the software stack — not real hardware.

| Project assumption | Reality | Verdict |
|---|---|---|
| 256×144, 6-bit (64-level) grayscale LCD | Exactly correct | ✅ |
| Wi-Fi = MT7921 monitor mode | MediaTek **MT7921AUN**, mainline mt76/nl80211 | ✅ (radio is separate from the RK3576 SoC) |
| BLE via BlueZ | Bluetooth 5.2, standard BlueZ/DBus on Debian | ✅ |
| NPU 6 TOPS, RKLLM backend stubbed pending driver (issue #55) | 6 TOPS; NPU driver **not in mainline yet** | ✅ correctly de-risked |
| UI = author HTML/CSS, render on device | FlipCTL **is real**: HTML/JS/CSS on **headless WebKit on DRM** | ✅ the single best-aligned guess |
| Ship as a "FlipCTL plugin" | FlipCTL plugins are **menu wrappers around CLI tools**, not full-screen animated apps; final OS is immutable → apps are **Flatpak/AppImage** | ⚠️ **mismatch** |
| GPS via `gpsd` is a core mechanic | **No onboard GPS in any published spec. No IMU either.** | ⚠️ **mismatch — real risk** |
| CPU LLM (llama.cpp on A72) as launch path | Plausible on RK3576, no blocker | ✅ |

Sources: [CNX Software](https://www.cnx-software.com/2026/05/21/flipper-one-a-rockchip-rk3576-powered-portable-arm-linux-computer-and-networking-multi-tool/),
[Flipper One tech specs](https://docs.flipper.net/one/general/tech-specs),
[Wi-Fi/BT (MT7921AUN)](https://docs.flipper.net/one/hardware/wifi-bluetooth),
[FlipCTL blog](https://blog.flipper.net/flipctl-our-gui-framework-for-embedded-linux-systems/) /
[docs](https://docs.flipper.net/one/cpu-software/flipctl),
[NPU driver issue #55](https://github.com/flipperdevices/flipperone-linux-build-scripts/issues/55),
[RKLLM runtime](https://github.com/airockchip/rknn-llm).

### The "online demo" you heard about
There is **no hosted Flipper One emulator** that runs arbitrary third-party UIs. What
exists is the official **Figma UI prototype**
([assets library](https://www.figma.com/design/U4k0qHkl9JdCu17MEtLFdI/Flipper-One-UI-Assets-library),
[main board](https://www.figma.com/design/PhlEqdtgjFfcizdVV0qNSR/Flipper-One-UI---Main-board),
linked from [flipperone-ui](https://github.com/flipperdevices/flipperone-ui)) — a design
mock, not a runnable environment for this project's HTML. Beware false hits:
`playground.flippercloud.io` (a Ruby feature-flag SaaS) and `lab.flipp.dev` (the Flipper
*Zero* app catalog) are unrelated. **FAP files are Flipper Zero only — do not wire packaging toward FAP.**

---

## Priority 0 — Safety & correctness (do before any transmit on real hardware)

> **Status: DONE** (commit on `refactor/persistence-facade`). All five items below
> are fixed and covered by `tests/test_p0_safety.py` (11 tests). Note on item 4:
> the SSID mitigation strips control chars, caps length, and delimits the value —
> it closes terminal-injection and overflow and reduces prompt-injection surface,
> but does not claim full LLM prompt-injection immunity (impact is limited to the
> pet uttering attacker text; the default `canned` backend has no LLM at all).

These undermine the project's own stated safety guarantees. None is large.

1. **Gate bettercap deauth and honor `--dry-run`.**
   `core/wifi/backends.py`, `core/bettercap.py`. `make_backend()` forwards `is_authorized`
   only to `NativeBackend`, never to `BettercapBackend`, and `BettercapClient` has no
   `dry_run` handling — so `_capture_handshake_live` **always** sends `wifi.deauth`.
   `cmd_capture` prints "DRY-RUN / none sent" or "PASSIVE / no deauth" and then transmits
   anyway. Since bettercap is the default when native tools are absent, the headline
   "deliberate per-AP, not mass deauth" guarantee is **not enforced end-to-end today.**
   *Effort: ~0.5 day.*

2. **Scope-gate on-the-fly cracking.**
   `agent.py` (`_field_battle` / `_field_consent`, ~248–279). Live deauth is properly gated
   per-target (`consent AND (manual OR in_scope)`), but the crack that follows a catch is
   gated only by a global "don't ask again" flag with **no `in_scope` check** — so once
   consent is dismissed the daemon will try to crack *any* network it catches. Cracking is
   arguably the most sensitive action and is the one that is scope-unaware. *Effort: small.*

3. **Audit the autonomous loop.**
   `core/authz.py` + agent call sites. Only the standalone `capture`/`cloud`/`battle`
   commands call `Authorizer.require`; the agent's deauth and crack **never** do, so the
   primary running mode produces no audit trail despite the README's "every active action
   is logged" claim. Add BLE actions to `ACTIVE_ACTIONS` too (active GATT connect / crackle
   / GATT-write are currently unlogged). *Effort: small.*

4. **Sanitize untrusted SSID text.**
   `ai/service.py`, `agent.py`. Attacker-controlled SSIDs flow unsanitized into (a) the LLM
   *user* prompt (prompt-injection: a crafted SSID can steer the pet's speech) and (b)
   `print()` (terminal/ANSI injection; also no hard length cap, so a chatty model overflows
   the 256×144 display). Delimit/escape SSIDs in prompts, strip control chars, and cap
   spoken/logged length. *Effort: small.*

5. **Remove shipped weak defaults.**
   `config.py:74–75`, `config.example.toml`. `bettercap_user="user"` / `bettercap_pass="pass"`
   ship as defaults; cloud API keys sit in plaintext config. Blank the creds and warn if
   left default. *Effort: trivial.*

---

## Priority 1 — Blocks running as a real app on-device

### The biggest structural gap: no device UI or input layer
Every interaction today is a terminal TUI (`os.system("clear")`, `print`, `input()`),
stdin prompts, or an HTML file written to `/tmp/flippergotchi/*.html`. On a real Flipper
One there is **no controlling terminal**: the pet can't be seen, driven, *or consented to*
(interactive consent falls back to "no/paused" when `stdin.isatty()` is false, so active
ops could only be enabled by hand-editing `prefs.json`). Concretely:

6. **Split render from output, then build a real device target.**
   All `view/*_screen.py` + `flipctl.py`. Despite its name, `view/flipctl.py` is just
   "write a full standalone HTML document to disk"; there is **no `Renderer`/`Canvas`
   backend** — every screen hardwires "build one giant HTML doc + `open().write()`". Extract
   pure `render_*() -> html_string` functions and move file I/O into one pluggable sink
   (file / screenshot / device). This is mostly mechanical because the target *is* HTML.
   *Effort: medium.* Then prototype the device target (below).

7. **Resolve the app-delivery model — the riskiest UI assumption.**
   The README's "wrap the markup in a FlipCTL plugin" step is likely wrong: FlipCTL plugins
   are D-pad menu wrappers around CLI tools, whereas Flippergotchi is a full-bleed animated
   game, and the final immutable "Flipper OS" ships third-party apps as **Flatpak/AppImage**.
   Decide now: sandboxed full-screen WebKit app (most likely) vs. FlipCTL plugin. Validate
   before investing more in UI. *Effort: research + medium.*

8. **Replace file-per-frame animation with live DOM updates.**
   `flipctl.render()` rewrites `face.html` every tick; `capture_screen`/`blebattle_screen`
   write N HTML files per animation. The real renderer is a *persistent* WebKit instance —
   reloading a full document per frame will flicker and won't animate. Push DOM/state deltas
   into the live renderer instead. *Effort: medium.*

9. **Add real input routing.** `battle_menu.BUTTONS` hardcodes labels ("OK/Up/Down/Back")
   but nothing wires D-pad/soft-buttons to actions. Needed for any on-device interaction and
   for a non-TTY consent surface. *Effort: medium.*

### Deployment & lifecycle

10. **Handle SIGTERM.** `agent.py` run loop catches only `KeyboardInterrupt`; there is no
    `signal`/`atexit` handler. systemd stop/shutdown sends SIGTERM → Python exits without
    running `finally: self._save()`, losing up to 10s of progress on every service stop.
    *Effort: small.*

11. **Ship a service + config-path story.** No systemd unit, no autostart, no default config
    search path (`Config.load` returns pure defaults unless `-c` is passed). Add a unit with
    `Restart=on-failure`, `AmbientCapabilities=CAP_NET_ADMIN CAP_NET_RAW`,
    `StateDirectory=flippergotchi`, explicit `HOME`/`User`, and a `/etc/flippergotchi/config.toml`
    search path. *Effort: medium.*

12. **Fix state-dir resolution under systemd.** All state is `~/.flippergotchi/*` via
    `expanduser`. Under systemd without `HOME`, `expanduser("~")` returns literal `~`,
    creating `./~/.flippergotchi` in the service CWD. Introduce a configurable `state_dir`.
    *Effort: small–medium.*

13. **aarch64 packaging for the CPU AI path.** The documented launch-day AI backend
    (`llama-cpp-python`) is a C++ extension with no cross-arch wheel pinned; CI is x86-only.
    Provide/pin an aarch64 wheel and add an aarch64 (or at least bleak/BlueZ) CI job.
    `numpy`/`Pillow` are dev-only (`tools/`), not runtime — good. *Effort: medium.*

### Decide the movement mechanic (GPS)

14. **The walking economy depends on hardware the device doesn't have.**
    The Flipper One spec lists **no onboard GPS and no IMU**, yet "walking is the fitness
    core" (XP → levels → evolutions, foraging food/gear) rests on it, and the roadmap's
    "IMU pedometer fallback" is also impossible. `pet/gps.py`'s `_gpsd_step` is actually
    fully implemented (contradicting its own "TODO" docstring and the README), but it can
    only work with an **externally attached** USB/UART GPS via gpsd. Pick a real movement
    source (external GNSS dongle, optional M.2 modem GNSS, phone tether, or a
    Wi-Fi/BLE-scan-derived motion heuristic) and correct the README. Until then, also
    **sanity-clamp fixes** before they feed the economy: filter TPV `mode >= 2`, reject
    teleport jumps, cap per-poll metres — today one bad fix injects unbounded XP/scrap.
    *Effort: small (docs/clamp) → large (new movement source).*

---

## Priority 2 — Reliability & hardening

**WiFi (`core/wifi/*`, `core/bettercap.py`):**
- `hcxdumptool` invocation uses stale flags and won't start on a current build: `-w`→`-o`,
  `--stop_after=<sec>` → `--tot=<minutes>` (min 2 min), and `--disable_disassociation`
  doesn't exist. Add a `--version` probe and build flags per version.
- `interface="mon0"` never exists — nothing creates it; `MonitorInterface` produces
  `wlan0`/`wlan0mon`. `doctor` false-negatives and bettercap targets a dead iface. Reconcile
  naming (prefer creating a dedicated monitor vif: `iw dev wlan0 interface add mon0 type monitor`).
- Don't `airmon-ng check kill` blindly — on a handheld the MT7921 may also be the uplink;
  add a monitor vif instead of tearing down NetworkManager/wpa_supplicant.
- **Lean on PMKID; treat deauth-driven 4-way and all 6 GHz capture as experimental** —
  mt7921u injection is documented-flaky and active monitor mode can hang the driver
  ([mt76 #839](https://github.com/openwrt/mt76/issues/839),
  [USB-WiFi #387](https://github.com/morrownr/USB-WiFi/issues/387)).
- bettercap handshake detection has no freshness filter (matches stale buffered events →
  false "caught"); surface 401/refused instead of silently returning `[]`; fix 6 GHz band
  mislabeling; add `CAP_NET_RAW` to the privilege probe.
- *What's solid:* `core/handshake.py` (pure-Python EAPOL/PMKID validation) is the best real
  code in the tree; the PMKID-first instinct and 6 GHz PSC channel plan are right.

**BLE (`core/bluetooth.py`):**
- **Use one long-lived asyncio loop.** Today every `poll()`/`enumerate()`/`_gatt_write()`
  calls `asyncio.run(...)`; bleak's BlueZ manager is meant to live once, and repeated loop
  teardown is the documented cause of `BleakDBusError`/stuck scans
  ([bleak #1272](https://github.com/hbldh/bleak/issues/1272),
  [#744](https://github.com/hbldh/bleak/issues/744)). This is the #1 BLE bug for hardware.
- Move BLE scan+enumerate off the synchronous tick (a 2.5s scan + serial 8s connects per
  device can freeze the loop for tens of seconds); reuse the discovered `BLEDevice` instead
  of connecting by bare MAC; handle "already in an event loop"; add a BlueZ/adapter check to
  `doctor`.
- Peer duels are **local-only** — they fight cached advertised stats and never contact the
  other device; either implement a real BLE exchange or relabel. BLE crackle is effectively
  dead code (needs a sniffed-pairing pcap nothing produces).

**AI (`ai/*`):**
- Fix the fallback chain: `build_backend()` does `npu → canned`, never `npu → cpu → canned`.
- **Make generation non-blocking** — it currently runs synchronously in `tick()`, so the pet
  freezes for the whole generate (seconds on A72/NPU). Emit the canned line instantly, run
  the model on a worker thread, swap the text when done, with a hard timeout.
- The NPU backend is a stub on a **fictional API** (`from rkllm_runtime import RKLLM` doesn't
  exist). Real path: **ctypes bindings over `librkllmrt.so`** (`rkllm_init`/`rkllm_run`
  blocking-with-callback/`rkllm_destroy`), model converted to **`.rkllm`** on an x86 PC via
  RKLLM-Toolkit (`w4a16` on RK3576). Version-pin the ctypes struct layout to the shipped
  `.so` or `rkllm_init` silently corrupts. Recommended model: **Qwen2.5-0.5B-Instruct** for
  latency (or 1.5B w4a16 for richer voice, ~8–12 tok/s). *Blocked on NPU driver anyway (#55) —
  canned/cpu are launch-ready.*

**UI fidelity (`view/*`, `tools/device_gray.py`):**
- Add **dithering** to the 6-bit conversion (posterize-only truncation bands; every screen
  uses gradients/blurred shadows that will visibly band on 64 levels), and run it on the
  live render path, not just docs PNGs.
- **Color-as-information collapses in grayscale** — rarity `#5aa9ff`/`#c07bf0` and HP
  green/yellow/red map to near-identical luma. Add redundant cues (patterns, borders, letters).
- Audit 6–8px fonts under device WebKit (`DejaVu Sans Mono` likely absent, no AA at ~123 ppi);
  fix `badge_screen.py` `columns:2 + overflow:hidden` silently clipping badges; reduce blurred
  shadows/gradients (costly to composite on ARM software WebKit).
- Commit the missing HTML→PNG step: a Playwright/WebKit screenshot harness at a 256×144
  viewport → `device_gray` with dither. This is also the **closest faithful proxy for testing
  the UI today** (render under WebKit, not desktop Chrome).

**Persistence / maintainability:**
- `agent.py` was intentionally not migrated to `GameState` (it owns a `TrackerLog` the facade
  doesn't model). Not a bug today (separate processes save disjoint sets), but the two
  hand-maintained store lists (`agent._save` saves trackers-not-prefs; `GameState.save` saves
  prefs-not-trackers) will drift. Unify by adding `trackers` to `GameState`. Consider a
  lockfile for CLI/daemon races on shared `peers.json`/`prefs.json`.
- Fix version mismatch: `pyproject.toml` `0.9.0` vs `__init__.py` `0.0.1`.

---

## Recommended sequencing

1. **P0 safety batch (items 1–5)** — ~2–3 days, closes the gap between advertised and actual
   safety behavior. Do this first; it's small and it's the credibility of the whole project.
2. **De-risk the two biggest unknowns in parallel** — (a) prove the UI renders correctly
   through real FlipCTL/WebKit and settle Flatpak-vs-plugin (item 7); (b) decide the movement
   mechanic (item 14). Both are "measure before you build" and gate large downstream work.
3. **Device edges (items 6, 8–13)** — the UI/input/deploy plumbing that makes it a real app.
4. **P2 hardening** — as each subsystem gets real hardware to validate against.

## What the project got right (don't touch)
Clean sim/hardware backend seam; correct MT7921/mt76 + BLE/BlueZ + display targeting;
solid pure-Python handshake validation; PMKID-first instinct; fail-closed authz with a
JSONL audit trail; the HTML-at-256×144-grayscale UI bet matching real FlipCTL/WebKit; and
pervasive honest "NEEDS ON-HARDWARE VALIDATION" tagging. The bones are good.
