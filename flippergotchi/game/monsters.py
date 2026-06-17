"""APs and Bluetooth devices, reimagined as collectible monsters."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .analysis import assess

# encryption -> WiFi species (the "armor class" of the creature)
_WIFI_SPECIES = {
    "open": "Wispling",
    "wep": "Rustbug",
    "wpa": "Wavemon",
    "wpa2": "Crypterion",
}
# band -> element
_ELEMENT = {"2.4GHz": "Spark", "5GHz": "Tide", "6GHz": "Gale"}
# BLE device-class -> mini species
_BLE_SPECIES = {
    "phone": "Pocketling", "wearable": "Tickbit", "audio": "Echobub",
    "beacon": "Blip", "computer": "Cogling", "tracker": "Trackling",
    "input": "Keytapper", "smarthome": "Hearthkin", "medical": "Vitalix",
    "unknown": "Pixie",
}
# BLE vendor "faction" -> element (flavour / future BLE matchups)
_BLE_ELEMENT = {"Apple": "Aether", "Google": "Spark", "Samsung": "Tide",
                "Microsoft": "Gale", "Garmin": "Gale", "Xiaomi": "Tide"}
# device-class -> rarity tier (trackers are the prized/uneasy find)
_BLE_RARITY = {"tracker": "rare", "medical": "uncommon", "input": "uncommon",
               "smarthome": "uncommon"}


@dataclass
class Monster:
    id: str                 # bssid (wifi) or address (ble)
    kind: str               # "wifi" | "ble"
    name: str               # ssid or device name
    species: str
    element: str
    level: int
    hp: int
    defense: int            # = crack difficulty (0..100)
    encryption: str = ""
    signal: int = 0         # dBm
    band: str = ""
    clients: int = 0
    seen: int = 1           # times encountered
    captured: bool = False  # handshake/scan obtained
    defeated: bool = False  # cracked / tamed
    key: str = ""           # recovered PSK, once defeated
    attempts: int = 0       # battles fought against it
    last_result: str = ""   # raw result of the most recent battle
    capture_path: str = ""  # on-disk handshake/PMKID capture (for cloud upload)
    rarity: str = ""        # BLE tier: common|uncommon|rare (flavour/display)
    vendor: str = ""        # BLE vendor faction (Apple/Google/...)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Monster":
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in d.items() if k in known})


_PLACEHOLDER_ID = "00:00:00:00:00:00"


def is_valid_id(bssid: str) -> bool:
    return bool(bssid) and bssid not in ("?", _PLACEHOLDER_ID)


def label(m: "Monster") -> str:
    """Display name; hidden/unnamed APs fall back to a per-BSSID label so two
    different hidden networks never look like the same one."""
    if m.name and m.name not in ("<hidden>", "(unnamed)", "?", ""):
        return m.name
    return f"<hidden {m.id[-5:]}>"


def from_ap(ev: dict) -> Monster:
    a = assess(ev)
    enc = a.encryption
    band = ev.get("band", "2.4GHz")
    defense = a.difficulty
    return Monster(
        id=a.bssid, kind="wifi", name=a.ssid,
        species=_WIFI_SPECIES.get(enc, "Crypterion"),
        element=_ELEMENT.get(band, "Spark"),
        level=max(1, round(defense / 8) + ev.get("clients", 0)),
        hp=20 + defense,
        defense=defense, encryption=enc, signal=ev.get("signal", -60),
        band=band, clients=ev.get("clients", 0),
        captured=(ev.get("kind") in ("handshake", "pmkid")),
    )


def from_ble(ev: dict) -> Monster:
    """Build a BLE mini-monster from an enriched advertisement event.

    Species comes from the device class, element from the vendor faction, and
    the level/rarity scale with signal strength + how much the device advertises
    (more services = a meatier creature). `captured=True` marks a *sighting*
    (collected by scanning); a later GATT enumerate "tames" it (sets defeated).
    """
    cls = (ev.get("device_class") or ev.get("appearance") or "unknown").lower()
    rssi = int(ev.get("rssi", -70) or -70)
    vendor = str(ev.get("company", "") or "")
    services = ev.get("services") or []
    nservices = len(services) if isinstance(services, (list, tuple)) else 0

    level = max(1, 3 + (rssi + 100) // 20 + min(nservices, 4))
    rarity = _BLE_RARITY.get(cls, "common")
    # trackers and medical kit are a bit hardier; richer adverts = more HP
    hp = 8 + nservices * 2 + (6 if cls == "tracker" else 0)
    defense = 5 + (5 if rarity == "rare" else 2 if rarity == "uncommon" else 0)

    return Monster(
        id=ev.get("addr", "00:00:00:00:00:00"), kind="ble",
        name=ev.get("name") or "(unnamed)",
        species=_BLE_SPECIES.get(cls, "Pixie"),
        element=_BLE_ELEMENT.get(vendor, "Aether"),
        level=level, hp=hp, defense=defense, signal=rssi,
        rarity=rarity, vendor=vendor,
        captured=True,   # sighting = lightly collected; GATT enum = fully tamed
    )
