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
    "wpa2-eap": "Bastion",
    "wpa3": "Saebercat",
    "wpa3-sae": "Saebercat",
    "owe": "Mistwalker",
}
# band -> element
_ELEMENT = {"2.4GHz": "Spark", "5GHz": "Tide", "6GHz": "Gale"}
# BLE appearance -> mini species
_BLE_SPECIES = {
    "phone": "Pocketling", "wearable": "Tickbit", "audio": "Echobub",
    "beacon": "Blip", "computer": "Cogling", "unknown": "Pixie",
}


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

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Monster":
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in d.items() if k in known})


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
    appearance = (ev.get("appearance") or "unknown").lower()
    rssi = ev.get("rssi", -70)
    return Monster(
        id=ev.get("addr", "00:00:00:00:00:00"), kind="ble",
        name=ev.get("name") or "(unnamed)",
        species=_BLE_SPECIES.get(appearance, "Pixie"),
        element="Aether",
        level=max(1, 3 + (rssi + 100) // 20),  # closer = a bit stronger
        hp=10, defense=5, signal=rssi,
        captured=True,  # a BLE creature is "tamed" just by scanning it
    )
