from __future__ import annotations

import random


class BluetoothScanner:
    """Source of Bluetooth/BLE devices -> small monsters.

    mode="sim"  -> emits fake BLE devices for development
    mode="live" -> BLE advertising scan via `bleak` (BlueZ on Linux) translated
                   into {type, addr, name, appearance, rssi} device events and
                   {type, addr, name, level, handshakes, gear_power} peer events.

    NOTE: the live path needs validation on real hardware with BlueZ + bleak.
    It has been written defensively (lazy import, broad except, never raises)
    but the exact advertisement payloads should be smoke-tested on a device.

    ------------------------------------------------------------------------
    Flippergotchi PEER advertising convention (so the broadcasting side can
    match it):

      * The BLE local name MUST start with the prefix "FG-".
      * After the prefix the format is:  FG-<name>-L<level>-H<handshakes>-G<gear>
        e.g.  "FG-Sparkfin-L7-H12-G20"
          - <name>        : peer's display name (no dashes)
          - L<level>      : integer level
          - H<handshakes> : integer handshake count
          - G<gear>       : integer gear power
      * Any of the L/H/G segments may be omitted; missing values fall back to
        sensible defaults (level=1, handshakes=0, gear_power=0).
      * A device whose name merely starts with "FG-" but carries no parsable
        stats is still treated as a peer (with defaults), so a minimal beacon
        advertising just "FG-Whoever" works.
    ------------------------------------------------------------------------
    """

    # bleak's BLE "appearance" value isn't reliably exposed across backends,
    # so we map advertised service UUIDs / heuristics to our coarse buckets.
    def __init__(self, cfg):
        self.cfg = cfg
        self.mode = "sim" if cfg.simulate else "live"
        # guard so the "bleak not installed" warning is logged at most once
        self._warned_no_bleak = False
        # scan window in seconds (kept short so poll() stays responsive)
        self._scan_timeout = float(getattr(cfg, "bluetooth_scan_timeout", 2.5))

    def poll(self) -> list:
        if self.mode != "sim":
            return self._poll_live()
        # occasionally another Flippergotchi is nearby (advertises name + stats)
        if random.random() < 0.05:
            return [{
                "type": "peer",
                "addr": ":".join("%02X" % random.randint(0, 255) for _ in range(6)),
                "name": random.choice(["Sparkfin", "RogueDolphin", "ByteSurf",
                                       "NixWave", "GotchiX"]),
                "level": random.randint(1, 14),
                "handshakes": random.randint(0, 40),
                "gear_power": random.randint(0, 35),
                "element": random.choice(["Spark", "Tide", "Gale", "Aether"]),
            }]
        if random.random() < 0.15:
            appearance = random.choice(
                ["phone", "wearable", "audio", "beacon", "computer", "unknown"])
            return [{
                "type": "ble",
                "addr": ":".join("%02X" % random.randint(0, 255) for _ in range(6)),
                "name": random.choice(
                    ["Galaxy Buds", "Mi Band", "JBL Flip", "Tile", "iPhone",
                     "(unnamed)", "Fitbit", "AirPods"]),
                "appearance": appearance,
                "rssi": random.randint(-95, -45),
            }]
        return []

    # ------------------------------------------------------------------ live

    def _poll_live(self) -> list:
        """Run a short BLE discovery scan and translate the results.

        Any failure (no bleak, no adapter, no permissions, asyncio issues,
        unexpected advert shapes) results in an empty list -- poll() must never
        raise. Needs validation on real hardware with BlueZ + bleak.
        """
        try:
            import asyncio

            try:
                from bleak import BleakScanner  # type: ignore
            except Exception:
                if not self._warned_no_bleak:
                    self._warned_no_bleak = True
                    # Log once; fall through to the empty-list return below so we
                    # don't spam every poll cycle.
                    try:
                        import logging
                        logging.getLogger(__name__).info(
                            "bluetooth: live mode requested but `bleak` is not "
                            "installed; returning no devices. Install `bleak` "
                            "for real BLE scanning.")
                    except Exception:
                        pass
                return []

            async def _discover():
                # return_adv=True -> {address: (BLEDevice, AdvertisementData)}
                try:
                    return await BleakScanner.discover(
                        timeout=self._scan_timeout, return_adv=True)
                except TypeError:
                    # Older bleak without return_adv: fall back to device list.
                    devices = await BleakScanner.discover(
                        timeout=self._scan_timeout)
                    return {d.address: (d, None) for d in devices}

            discovered = asyncio.run(_discover())

            events = []
            for addr, pair in discovered.items():
                try:
                    device, adv = pair
                except Exception:
                    device, adv = pair, None
                ev = self._translate(addr, device, adv)
                if ev is not None:
                    events.append(ev)
            return events
        except Exception:
            # No adapter, permissions error, event-loop conflict, etc.
            return []

    def _translate(self, addr, device, adv):
        """Turn one discovered device into a ble/peer event, or None."""
        try:
            # Resolve the advertised local name from whichever source exists.
            name = None
            if adv is not None:
                name = getattr(adv, "local_name", None)
            if not name:
                name = getattr(device, "name", None)

            # RSSI: prefer AdvertisementData (device.rssi is deprecated).
            rssi = None
            if adv is not None:
                rssi = getattr(adv, "rssi", None)
            if rssi is None:
                rssi = getattr(device, "rssi", None)
            if rssi is None:
                rssi = -127
            try:
                rssi = int(rssi)
            except Exception:
                rssi = -127

            display_name = name if name else "(unnamed)"

            # --- Flippergotchi peer? name starts with the "FG-" prefix --------
            if name and name.startswith("FG-"):
                return self._parse_peer(addr, name)

            # --- otherwise a generic BLE device ------------------------------
            appearance = self._appearance(device, adv, name)
            return {
                "type": "ble",
                "addr": str(addr),
                "name": display_name,
                "appearance": appearance,
                "rssi": rssi,
            }
        except Exception:
            return None

    @staticmethod
    def _parse_peer(addr, name):
        """Parse "FG-<name>-L<lvl>-H<hs>-G<gear>" into a peer event.

        Missing segments fall back to defaults. Tolerant of extra/missing
        dashes so a bare "FG-Name" still yields a valid peer.
        """
        level, handshakes, gear_power = 1, 0, 0
        peer_name = "FG"
        body = name[3:]  # strip the "FG-" prefix
        segments = [s for s in body.split("-") if s != ""]

        name_parts = []
        for seg in segments:
            tag, rest = seg[:1].upper(), seg[1:]
            if tag in ("L", "H", "G") and rest.isdigit():
                val = int(rest)
                if tag == "L":
                    level = val
                elif tag == "H":
                    handshakes = val
                else:
                    gear_power = val
            else:
                name_parts.append(seg)

        if name_parts:
            peer_name = "-".join(name_parts)

        return {
            "type": "peer",
            "addr": str(addr),
            "name": peer_name,
            "level": level,
            "handshakes": handshakes,
            "gear_power": gear_power,
        }

    @staticmethod
    def _appearance(device, adv, name):
        """Best-effort coarse appearance bucket from advert hints.

        bleak doesn't reliably surface the GAP "appearance" field across
        backends, so we use service-UUID and name heuristics. Falls back to
        "unknown". Buckets must stay within the set the agent understands:
        phone / wearable / audio / beacon / computer / unknown.
        """
        try:
            uuids = []
            if adv is not None:
                uuids = [str(u).lower() for u in (
                    getattr(adv, "service_uuids", None) or [])]

            # Well-known 16-bit GATT service short codes (embedded in the
            # 128-bit base UUID as 0000XXXX-0000-1000-8000-00805f9b34fb).
            def has(short):
                frag = "0000%s-0000-1000-8000-00805f9b34fb" % short
                return any(frag in u for u in uuids)

            # Audio: A2DP-ish / Audio Source/Sink hints.
            if has("110a") or has("110b") or has("1108") or has("1203"):
                return "audio"
            # Wearable: Heart Rate (180d), Health Thermometer (1809),
            # Running/Cycling, Fitness Machine (1826).
            if has("180d") or has("1816") or has("1814") or has("1826"):
                return "wearable"
            # Beacon: Eddystone (feaa) / common iBeacon-style advert with no
            # connectable services.
            if has("feaa"):
                return "beacon"

            n = (name or "").lower()
            if any(k in n for k in ("buds", "airpods", "jbl", "headphone",
                                    "speaker", "soundcore")):
                return "audio"
            if any(k in n for k in ("band", "watch", "fit", "tracker")):
                return "wearable"
            if any(k in n for k in ("iphone", "galaxy", "pixel", "phone")):
                return "phone"
            if any(k in n for k in ("macbook", "thinkpad", "pc", "laptop",
                                    "desktop")):
                return "computer"
            if any(k in n for k in ("tile", "beacon")):
                return "beacon"
        except Exception:
            pass
        return "unknown"
