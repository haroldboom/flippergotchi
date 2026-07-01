# Movement source: options + recommendation (P1 item 14)

*Decision-support memo. The walking/fitness economy is a core mechanic, but the
Flipper One lacks the hardware the current design assumes. This lays out the real
options and recommends one. No app code changed. `pet/gps.py` is being hardened
by another agent -- this memo references its `GpsReader` abstraction and does not
edit it.*

---

## The problem (verified)

"Walking is the fitness core" of the game economy: metres travelled feed XP ->
levels -> evolutions, plus foraging (food/gear). Today `pet/gps.py`'s `GpsReader`
turns "metres since last poll" into that economy via `distance()`, with modes
`sim` (random wander), `gpsd` (real, TCP JSON to `127.0.0.1:2947`), and `off`.

But:

* **The Flipper One has NO onboard GPS/GNSS.** The tech specs list no positioning
  hardware.
* **It has NO IMU** (no accelerometer/gyroscope) -- so the roadmap's "IMU
  pedometer fallback" is also impossible.

Verified: [Flipper One tech specs](https://docs.flipper.net/one/general/tech-specs)
list display, power meter, Wi-Fi/BT, Ethernet PHY, audio codec, and fuel gauge --
**no GNSS, no IMU**.

So `GpsReader`'s `gpsd` path can only work against an **externally supplied**
position source. The question is which one.

---

## Options

### (a) External USB/UART GNSS dongle via `gpsd`

* **Needs:** a u-blox-class USB or UART GNSS receiver plugged into the device;
  `gpsd` running; `gps_mode="gpsd"`. This is *already implemented* in
  `_gpsd_step()` (contradicting its own stale "TODO" docstring).
* **Fidelity:** high -- true few-metre positioning, real outdoor walk tracking.
* **UX:** a dongle hanging off a handheld is bulky; needs sky view; cold-start
  lag. But it is the "it just works like Pokemon-GO-walking" experience.
* **Cost:** ~zero code (path exists); needs the sanity-clamping the review asked
  for (filter TPV `mode>=2`, reject teleport jumps, cap metres/poll) before it
  feeds the economy. Depends on the user owning/attaching hardware.

### (b) GNSS via an M.2 module (**first-class, supported add-on**)

* **Needs:** an M.2 **GNSS receiver** module in the Flipper One's M.2 slot. This
  is a **documented, supported module category** -- Flipper's own M.2 modules page
  lists *"gnss modules add satellite positioning (gps, glonass, galileo, beidou)
  for location aware applications."* Such a module would present as a serial/USB
  GNSS device -> `gpsd` -> **the exact same `gpsd` path as (a)**.
* **Important correction:** GNSS is a **dedicated** M.2 category. The **cellular
  modem** and **satellite modem** categories are described as *connectivity* only
  and are **not** documented to provide positioning -- so do **not** assume "the
  optional cellular modem gives you GNSS." Some real cellular modems bundle a GNSS
  receiver, but that is per-module and unverified for any Flipper-blessed part.
* **Fidelity:** high (same as (a)); integrated (no dangling dongle) if a module
  exists.
* **UX:** clean if the user has the module; but it competes for the single M.2
  slot with the SDR/cellular/AI modules the rest of the app may want.
* **Cost:** ~zero incremental code beyond (a) -- it collapses into the same gpsd
  reader. Depends on module availability. **[NEEDS HARDWARE]** -- no shipping
  Flipper GNSS M.2 part is finalized yet (device isn't shipping).

Verified: [M.2 modules](https://docs.flipper.net/one/hardware/m2-port/modules)
(GNSS is a listed category), [M.2 port](https://docs.flipper.net/one/hardware/m2-port).
Unverified: that any specific GNSS module ships, and that cellular/satellite
modems expose GNSS.

### (c) Wi-Fi/BLE-scan motion heuristic (no extra hardware)

* **Needs:** nothing new -- the device already scans Wi-Fi (MT7921) and BLE
  (BlueZ) for the core game. Infer *movement* (not position) from the churn in the
  set of visible APs/BLE devices and their RSSI between scans: high churn / large
  RSSI deltas -> moving; a stable set of BSSIDs at stable RSSI -> stationary.
  Convert "fraction of environment changed per interval" into a synthetic
  "distance" or an "active minutes" signal.
* **Fidelity:** coarse. This is a *movement/activity* detector, not a
  pedometer or odometer -- it cannot give real metres, and it degrades where the
  environment is sparse (rural) or where APs move with you (a train, a phone
  hotspot in your pocket). It's a well-studied technique for motion/occupancy
  detection (Wi-Fi RSSI motion sensing, ~94% motion/no-motion classification in
  the literature), but "how far did you walk" from AP-set churn is an
  *approximation with no ground-truth calibration.*
* **UX:** best-in-class -- zero setup, no accessory, works indoors, collects no
  location. Naturally privacy-friendly (matches the project's ethos). Gracefully
  degrades to "some activity credited" rather than "nothing works."
* **Cost:** medium -- a new heuristic + tuning, and honest game-economy design so
  it can't be gamed (a busy cafe would otherwise mint XP while you sit still; a
  churn signal must gate on *changing* sets, and rate-limit credit).
* **Anti-cheat / honesty:** must be framed to the player as "activity" not
  "distance," or it will feel broken when it disagrees with a real walk.

Evidence that Wi-Fi RSSI motion inference is real (though not turn-key pedometry):
[MDPI: WiFi motion for health](https://www.mdpi.com/2306-5354/10/2/228),
[arXiv survey: CSI/RSSI human motion](https://arxiv.org/pdf/2506.12052),
[ESP32 RSSI motion detector](https://github.com/happytm/MotionDetector).

### (d) Phone-tethered location

* **Needs:** a companion phone app (or a BLE/Wi-Fi bridge) that forwards the
  phone's GPS to the Flipper; the Flipper consumes it (ideally re-exposed through
  gpsd so it reuses (a)'s path).
* **Fidelity:** high (phone GNSS is excellent).
* **UX:** high friction -- requires a second app, pairing, permissions, battery on
  two devices; couples the "standalone cyberdeck" to a phone, which cuts against
  the product's identity.
* **Cost:** large -- a whole companion app + protocol + pairing UX. Highest total
  cost of the "real position" options.

### (e) Redesign the mechanic to not require movement

* **Needs:** decouple XP/evolution/foraging from metres. Drive progression from
  what the device *does* have: successful captures, BLE encounters/duels, uptime/
  care, daily streaks, "expeditions" (time-boxed scan sessions), foraging from
  *networks discovered* rather than *distance walked*.
* **Fidelity:** n/a -- it removes the dependency entirely.
* **UX:** always works, on every unit, day one, with no accessory. Loses the
  "go outside and walk" hook that makes it a *fitness* pet, which some of the
  product identity rests on.
* **Cost:** medium -- game-economy rebalancing, but no hardware/driver risk.

---

## Recommendation

> **Tier it. Ship (e) + (c) as the default, and treat (a)/(b) as an optional
> high-fidelity upgrade through the existing gpsd path. Do not build (d).**

Concretely:

1. **Default, works on every unit (no accessory):** make the economy earn from
   *activity + play* (option (e)) and layer the **Wi-Fi/BLE-scan motion heuristic
   (c)** on top as an "activity" signal. This guarantees the game is fully
   playable on a bare Flipper One on day one, honestly, with no false hardware
   promise -- and it reuses radios the app already drives.
2. **Optional high-fidelity "real walking":** anyone with an **external USB/UART
   GNSS dongle (a)** or an **M.2 GNSS module (b)** gets true metres -- for *free*,
   because both feed `gpsd` and collapse into the single existing `gpsd` reader.
   Advertise this as an enhancement, not a requirement.
3. **Drop (d)** unless a companion app is being built for other reasons -- highest
   cost, worst fit with the standalone identity.
4. **Correct the README/roadmap:** remove "IMU pedometer fallback" (no IMU
   exists) and reframe walking as an *optional GNSS-upgraded* mechanic over an
   activity baseline. *(README edit left to the owning change.)*

Rationale: (a) and (b) are near-free but hardware-gated and unavailable at
launch; the game still has to be great on a bare device. (c)+(e) make that true
without over-promising, and the gpsd seam means adding real GNSS later is a config
flip, not a rewrite.

---

## Migration sketch (fits the existing `GpsReader`)

`GpsReader` already exposes the right seam: **one method, `distance() -> float`
metres since last poll**, selected by `cfg.gps_mode` (`sim`/`gpsd`/`off`). Keep
that contract; extend it, don't replace it.

* **(a)/(b) -- GNSS:** already the `gpsd` mode. No structural change; just land
  the review's sanity-clamps *inside* `_gpsd_step()` (drop TPV `mode<2`, reject
  teleport jumps, cap metres/poll) so a bad fix can't inject unbounded XP/scrap.
  An M.2 GNSS module is transparent -- it presents to gpsd like any receiver.
* **(c) -- scan heuristic:** add a new mode, e.g. `gps_mode="scan"`, backed by a
  new `_scan_step()` that reads the Wi-Fi/BLE scan results the app already
  collects and returns a **bounded** synthetic distance (or, cleaner, expose a
  sibling `activity()` signal the economy consumes when no real GNSS is present).
  Keep it behind the same `distance()`/reader interface so game logic is unchanged.
* **(e) -- redesign:** lives in the economy layer (`pet/mechanics.py` and the
  agent), largely orthogonal to `GpsReader`; with `gps_mode="off"`, `distance()`
  returns 0 and progression comes entirely from play. (c) simply *adds* an
  activity trickle on top.

Net: the abstraction is right. The work is (1) clamps on the existing gpsd path,
(2) a new `scan` reader mode, and (3) economy rebalancing so the game is complete
without any position hardware -- all additive, none of it a rewrite.

---

## Sources

* Flipper One tech specs (no GPS, no IMU): https://docs.flipper.net/one/general/tech-specs
* M.2 modules -- GNSS is a supported category; cellular/satellite are connectivity only: https://docs.flipper.net/one/hardware/m2-port/modules
* M.2 port: https://docs.flipper.net/one/hardware/m2-port
* Wi-Fi motion sensing (health): https://www.mdpi.com/2306-5354/10/2/228
* CSI/RSSI human-motion survey: https://arxiv.org/pdf/2506.12052
* ESP32 RSSI motion detector (precedent): https://github.com/happytm/MotionDetector
* gpsd JSON/TPV protocol (the reader's wire format): https://gpsd.gitlab.io/gpsd/gpsd_json.html

*Verified = quoted from official Flipper docs. **[NEEDS HARDWARE]** = no Flipper
One ships yet, so no GNSS M.2 part is finalized and the scan heuristic's real-walk
accuracy can only be tuned/validated on a device with a ground-truth reference.*
