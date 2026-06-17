"""APs and Bluetooth devices, reimagined as collectible monsters."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .analysis import assess

# WiFi species now come from the AP's BRAND (vendor), not its encryption --
# WPA2/open monsters are identified by who made the router. WEP and WPA(1) are
# rare, trivially-cracked LEGENDARIES instead (legacy security = a prized find).
_WIFI_VENDOR_SPECIES = {
    "Netgear": "Gnashgear",
    "TP-Link": "Mantalink",
    "Linksys": "Synksquid",
    "ASUS": "Asurpent",
    "Cisco": "Kragnet",
    "ISP": "Telewyrm",
}
# weak/legacy encryption -> legendary species (any vendor)
_LEGENDARY_SPECIES = {"wep": "Wepwraith", "wpa": "Wparchon"}
# unknown vendor (WPA2/open) falls back to the apex piranha
_UNKNOWN_WIFI_SPECIES = "Crypterion"
# every WiFi species (for sprite-coverage checks)
_WIFI_SPECIES = {**_WIFI_VENDOR_SPECIES, **_LEGENDARY_SPECIES,
                 "unknown": _UNKNOWN_WIFI_SPECIES}

# SSID keyword -> vendor faction (case-insensitive substring)
_WIFI_VENDOR_SSID = [
    ("netgear", "Netgear"), ("orbi", "Netgear"),
    ("tp-link", "TP-Link"), ("tplink", "TP-Link"), ("archer", "TP-Link"),
    ("deco", "TP-Link"),
    ("linksys", "Linksys"), ("velop", "Linksys"),
    ("asus", "ASUS"), ("rt-ac", "ASUS"), ("rt-ax", "ASUS"), ("zenwifi", "ASUS"),
    ("cisco", "Cisco"), ("meraki", "Cisco"), ("aironet", "Cisco"),
    ("xfinity", "ISP"), ("comcast", "ISP"), ("spectrum", "ISP"), ("att", "ISP"),
    ("verizon", "ISP"), ("telstra", "ISP"), ("optus", "ISP"), ("iinet", "ISP"),
    ("virgin", "ISP"), ("vodafone", "ISP"), ("sky", "ISP"), ("bt", "ISP"),
]
# BSSID OUI prefix (first 3 octets, upper) -> vendor, for real hardware where
# the SSID isn't brandy. A small starter set; extend as needed.
_WIFI_OUI = {
    "9C:3D:CF": "Netgear", "A0:40:A0": "Netgear", "C0:3F:0E": "Netgear",
    "50:C7:BF": "TP-Link", "AC:84:C6": "TP-Link", "C4:6E:1F": "TP-Link",
    "00:18:39": "Linksys", "48:F8:B3": "Linksys", "C0:56:27": "Linksys",
    "2C:56:DC": "ASUS", "AC:9E:17": "ASUS", "04:D4:C4": "ASUS",
    "00:1A:A1": "Cisco", "00:0B:85": "Cisco", "58:97:1E": "Cisco",
}


def _wifi_vendor(ssid: str, bssid: str) -> str:
    """Best-effort AP vendor from the SSID brand or the BSSID OUI."""
    s = (ssid or "").lower()
    for kw, vendor in _WIFI_VENDOR_SSID:
        if kw in s:
            return vendor
    oui = (bssid or "")[:8].upper()
    return _WIFI_OUI.get(oui, "")


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
    vendor = _wifi_vendor(a.ssid, a.bssid)
    # WEP / WPA(1) are the rare legendaries (legacy security = easy + prized);
    # everything else (WPA2 / open) is identified by the router's brand.
    if enc in _LEGENDARY_SPECIES:
        species, rarity = _LEGENDARY_SPECIES[enc], "legendary"
    else:
        species = _WIFI_VENDOR_SPECIES.get(vendor, _UNKNOWN_WIFI_SPECIES)
        rarity = ""
    return Monster(
        id=a.bssid, kind="wifi", name=a.ssid,
        species=species,
        element=_ELEMENT.get(band, "Spark"),
        level=max(1, round(defense / 8) + ev.get("clients", 0)),
        hp=20 + defense,
        defense=defense, encryption=enc, signal=ev.get("signal", -60),
        band=band, clients=ev.get("clients", 0),
        rarity=rarity, vendor=vendor,
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
