from __future__ import annotations

import logging
import random

log = logging.getLogger(__name__)

# BLE company identifiers (the keys of an advert's manufacturer_data) -> vendor.
# Used as a coarse "faction" hint for the monster taxonomy. Not exhaustive.
COMPANY_IDS = {
    76: "Apple", 6: "Microsoft", 224: "Google", 117: "Samsung", 158: "Bose",
    135: "Garmin", 89: "Nordic", 343: "Xiaomi", 488: "Logitech", 117: "Samsung",
}

# device-class buckets the game understands (species map keys in game/monsters)
DEVICE_CLASSES = ("phone", "wearable", "audio", "beacon", "computer",
                  "tracker", "input", "smarthome", "medical", "unknown")

# Probability per sim poll that a generic BLE device is emitted. Kept low so
# sim encounters are spaced out rather than firing on nearly every tick.
SIM_BLE_SPAWN_CHANCE = 0.05

# a small sim catalogue of realistic devices (name, vendor, advertised services,
# class, connectable) so simulation exercises the full taxonomy.
_SIM_DEVICES = [
    ("AirPods Pro", "Apple", ["audio_sink"], "audio", True),
    ("Galaxy Buds", "Samsung", ["audio_sink"], "audio", True),
    ("JBL Flip 6", "", ["audio_sink"], "audio", True),
    ("Mi Band 7", "Xiaomi", ["heart_rate"], "wearable", True),
    ("Fitbit Charge", "Google", ["heart_rate"], "wearable", True),
    ("iPhone", "Apple", [], "phone", False),
    ("Pixel 9", "Google", [], "phone", False),
    ("Tile Mate", "", ["tile"], "tracker", True),
    ("MX Keys", "Logitech", ["human_interface_device"], "input", True),
    ("Hue Lamp", "Signify", ["smarthome"], "smarthome", True),
    ("Contour Glucose", "Ascensia", ["glucose"], "medical", True),
    ("Eddystone", "", ["eddystone"], "beacon", False),
    ("ThinkPad", "Lenovo", [], "computer", True),
    ("(unnamed)", "", [], "unknown", False),
]
# a recurring "tracker that follows you" so the stalker-detection path is
# exercised in sim -- it reuses a FIXED address across ticks.
_STALKER = ("AirTag", "Apple", ["find_my"], "tracker", False)
_STALKER_ADDR = "C0:FF:EE:7A:65:71"


class BluetoothScanner:
    """Source of Bluetooth/BLE devices -> small monsters.

    mode="sim"  -> emits fake BLE devices (now with vendor/services/connectable)
                   for development.
    mode="live" -> BLE advertising scan via `bleak` (BlueZ on Linux) translated
                   into enriched device events, plus Flippergotchi peer events.

    Two interactions:
      * poll()            -- passive discovery (advertisements). Always allowed.
      * enumerate(addr)   -- ACTIVE GATT connect + service/characteristic
                             enumeration (the "tame"). The caller must authorize
                             it; this just performs the connect.

    Live paths need validation on real hardware with BlueZ + bleak; everything
    is written defensively (lazy import, broad except, never raises).

    ------------------------------------------------------------------------
    Flippergotchi PEER advertising convention (so the broadcasting side can
    match it):

      * The BLE local name MUST start with the prefix "FG-".
      * Format:  FG-<name>-L<level>-H<handshakes>-G<gear>
        e.g.  "FG-Sparkfin-L7-H12-G20" (any of L/H/G may be omitted).
    ------------------------------------------------------------------------
    """

    def __init__(self, cfg):
        self.cfg = cfg
        self.mode = "sim" if cfg.simulate else "live"
        self._warned_no_bleak = False
        self._scan_timeout = float(getattr(cfg, "bluetooth_scan_timeout", 2.5))

    # ------------------------------------------------------------------ poll
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
        # a recurring tracker tailing you (fixed addr -> triggers the alert)
        if random.random() < 0.04:
            return [self._sim_ble(_STALKER, addr=_STALKER_ADDR)]
        if random.random() < SIM_BLE_SPAWN_CHANCE:
            return [self._sim_ble(random.choice(_SIM_DEVICES))]
        return []

    def _sim_ble(self, profile, addr=None) -> dict:
        name, vendor, services, cls, conn = profile
        return {
            "type": "ble",
            "addr": addr or ":".join("%02X" % random.randint(0, 255)
                                     for _ in range(6)),
            "name": name,
            "appearance": cls,        # back-compat alias
            "device_class": cls,
            "company": vendor,
            "services": list(services),
            "connectable": conn,
            "tx_power": random.choice([None, -12, -6, 0, 4]),
            "addr_type": "random" if cls in ("phone", "tracker") else "public",
            "rssi": random.randint(-95, -45),
        }

    # ------------------------------------------------------------------ live
    def _poll_live(self) -> list:
        """Run a short BLE discovery scan and translate the results. Any failure
        (no bleak/adapter/permissions) -> []. Needs on-hardware validation."""
        try:
            import asyncio

            try:
                from bleak import BleakScanner  # type: ignore
            except Exception:
                if not self._warned_no_bleak:
                    self._warned_no_bleak = True
                    log.info("bluetooth: live mode requested but `bleak` is not "
                             "installed; returning no devices.")
                return []

            async def _discover():
                try:
                    return await BleakScanner.discover(
                        timeout=self._scan_timeout, return_adv=True)
                except TypeError:
                    devices = await BleakScanner.discover(timeout=self._scan_timeout)
                    return {d.address: (d, None) for d in devices}

            discovered = asyncio.run(_discover())
            events = []
            for addr, pair in discovered.items():
                try:
                    device, adv = pair
                except Exception:  # noqa: BLE001
                    device, adv = pair, None
                ev = self._translate(addr, device, adv)
                if ev is not None:
                    events.append(ev)
            return events
        except Exception:  # noqa: BLE001
            return []

    def _translate(self, addr, device, adv):
        """Turn one discovered device into an enriched ble/peer event, or None."""
        try:
            name = None
            if adv is not None:
                name = getattr(adv, "local_name", None)
            if not name:
                name = getattr(device, "name", None)

            rssi = None
            if adv is not None:
                rssi = getattr(adv, "rssi", None)
            if rssi is None:
                rssi = getattr(device, "rssi", None)
            try:
                rssi = int(rssi) if rssi is not None else -127
            except Exception:  # noqa: BLE001
                rssi = -127

            # Flippergotchi peer?
            if name and name.startswith("FG-"):
                return self._parse_peer(addr, name)

            # vendor from manufacturer_data company id (lowest key)
            company, company_id = "", None
            mfg = getattr(adv, "manufacturer_data", None) if adv else None
            if isinstance(mfg, dict) and mfg:
                try:
                    company_id = sorted(mfg.keys())[0]
                    company = COMPANY_IDS.get(int(company_id), "")
                except Exception:  # noqa: BLE001
                    company, company_id = "", None

            services = []
            if adv is not None:
                services = [str(u).lower() for u in
                            (getattr(adv, "service_uuids", None) or [])]

            tx_power = getattr(adv, "tx_power", None) if adv else None
            connectable = bool(getattr(adv, "connectable", True)) if adv else True
            addr_type = self._addr_type(addr)
            cls = self._classify(name, company, services, connectable)

            return {
                "type": "ble",
                "addr": str(addr),
                "name": name if name else "(unnamed)",
                "appearance": cls,        # back-compat alias
                "device_class": cls,
                "company": company,
                "company_id": company_id,
                "services": services,
                "connectable": connectable,
                "tx_power": tx_power,
                "addr_type": addr_type,
                "rssi": rssi,
            }
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _addr_type(addr) -> str:
        """Public vs random/resolvable, inferred from the address (best-effort).
        Random BLE addresses set the two MSBs of the first octet."""
        try:
            first = int(str(addr).split(":")[0], 16)
            return "random" if (first & 0xC0) else "public"
        except Exception:  # noqa: BLE001
            return ""

    @staticmethod
    def _parse_peer(addr, name):
        """Parse "FG-<name>-L<lvl>-H<hs>-G<gear>" into a peer event."""
        level, handshakes, gear_power = 1, 0, 0
        peer_name = "FG"
        segments = [s for s in name[3:].split("-") if s != ""]
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
        return {"type": "peer", "addr": str(addr), "name": peer_name,
                "level": level, "handshakes": handshakes, "gear_power": gear_power}

    @staticmethod
    def _classify(name, company, services, connectable) -> str:
        """Coarse device-class bucket from advertised services + name + vendor.
        Buckets must stay within DEVICE_CLASSES."""
        try:
            uuids = [str(u).lower() for u in (services or [])]

            def has(short):
                # accept a bare short code, a service keyword, or the 128-bit form
                frag = "0000%s-0000-1000-8000-00805f9b34fb" % short
                return any(short in u or frag in u for u in uuids)

            # trackers first (privacy-relevant): Find My / Tile / SmartTag.
            if has("find_my") or has("tile") or has("fd44") or has("feed"):
                return "tracker"
            if has("human_interface_device") or has("1812") or has("1124"):
                return "input"
            if has("smarthome") or has("fe0f") or has("hue"):
                return "smarthome"
            if has("glucose") or has("1808") or has("1810"):
                return "medical"
            if has("audio_sink") or has("110a") or has("110b") or has("110e"):
                return "audio"
            if has("heart_rate") or has("180d") or has("1816") or has("1826"):
                return "wearable"
            if has("eddystone") or has("feaa"):
                return "beacon"

            n = (name or "").lower()
            if any(k in n for k in ("airtag", "tile", "smarttag", "chipolo",
                                    "tracker", "find my")):
                return "tracker"
            if any(k in n for k in ("keyboard", "mouse", "keys", "mx ", "trackpad")):
                return "input"
            if any(k in n for k in ("bulb", "lamp", "hue", "lifx", "plug",
                                    "lock", "nest")):
                return "smarthome"
            if any(k in n for k in ("glucose", "oximeter", "thermometer", "bp ")):
                return "medical"
            if any(k in n for k in ("buds", "airpods", "jbl", "headphone",
                                    "speaker", "soundcore", "bose")):
                return "audio"
            if any(k in n for k in ("band", "watch", "fit", "garmin", "whoop")):
                return "wearable"
            if any(k in n for k in ("iphone", "galaxy", "pixel", "phone")):
                return "phone"
            if any(k in n for k in ("macbook", "thinkpad", "pc", "laptop",
                                    "desktop")):
                return "computer"
            if "beacon" in n:
                return "beacon"
        except Exception:  # noqa: BLE001
            pass
        return "unknown"

    # -------------------------------------------------------------- enumerate
    def enumerate(self, addr, timeout=None):
        """ACTIVE: connect to ``addr`` and enumerate its GATT services /
        characteristics (the "tame"). The CALLER must authorize this -- it
        connects to the device. Returns a dict::

            {"services": [name...], "characteristics": int, "device_info": {...}}

        or None on any failure. Never raises. NEEDS ON-HARDWARE VALIDATION."""
        if timeout is None:
            timeout = getattr(self.cfg, "ble_tame_timeout", 8.0)
        if self.mode == "sim":
            return self._sim_enumerate(addr)
        try:
            return self._enumerate_live(addr, float(timeout))
        except Exception as exc:  # noqa: BLE001
            log.warning("ble enumerate %s failed (%s)", addr, exc)
            return None

    @staticmethod
    def _sim_enumerate(addr) -> dict:
        """Deterministic synthetic GATT enumeration (same addr -> same result)."""
        h = sum(bytearray(str(addr).encode())) if addr else 0
        pool = ["generic_access", "generic_attribute", "device_information",
                "battery_service", "tx_power", "current_time", "heart_rate",
                "audio_sink", "human_interface_device", "immediate_alert"]
        n = 2 + (h % 5)
        svcs = sorted({pool[(h + i) % len(pool)] for i in range(n + 1)})
        return {"services": svcs, "characteristics": len(svcs) * 3,
                "device_info": {"manufacturer": "?", "model": "?"}}

    def _enumerate_live(self, addr, timeout):
        """bleak GATT enumeration. NEEDS ON-HARDWARE VALIDATION."""
        import asyncio
        try:
            from bleak import BleakClient  # type: ignore
        except Exception:
            return None

        async def _go():
            async with BleakClient(str(addr), timeout=timeout) as client:
                names, chars = [], 0
                for svc in client.services:
                    names.append(getattr(svc, "description", None)
                                 or str(getattr(svc, "uuid", "")))
                    chars += len(list(getattr(svc, "characteristics", []) or []))
                return {"services": names, "characteristics": chars,
                        "device_info": {}}

        return asyncio.run(_go())
