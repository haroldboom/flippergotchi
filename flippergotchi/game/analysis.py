"""Deterministic crack-difficulty assessment for a WiFi target.

This is the brain behind the "analyst" feature and every monster's defense
stat. It is pure heuristics (no model needed); the LLM layer just narrates it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Base difficulty by encryption: 0 = trivial .. 100 = infeasible with a wordlist.
ENC_DIFFICULTY = {
    "open": 0,
    "wep": 10,
    "wpa": 35,
    "wpa2": 55,
    "wpa2-eap": 90,
    "owe": 60,
    "wpa3": 95,
    "wpa3-sae": 95,
}

# SSID prefixes that hint at algorithmic / well-known default keys -> easier,
# because rockyou + default-key rules land them often. (prefix, why)
DEFAULT_HINTS = [
    ("NETGEAR", "NETGEAR default keys: two-words+digits, good rockyou hit-rate"),
    ("Linksys", "older Linksys defaults derive from the SSID"),
    ("TP-LINK", "TP-LINK label-default PSK patterns"),
    ("TPLINK", "TP-LINK label-default PSK patterns"),
    ("ATT", "AT&T defaults are 10-12 digit numeric (mask attack)"),
    ("SpectrumSetup", "Spectrum default = two-words style, high rockyou hit-rate"),
    ("BTHub", "BT Hub defaults come from a known wordlist"),
    ("HUAWEI", "Huawei vendor default-key patterns"),
    ("Telstra", "Telstra Gateway default-key patterns"),
]

_LABELS = [(1, "Trivial"), (16, "Easy"), (46, "Medium"), (71, "Hard"), (101, "Infeasible")]


def _label(d: int) -> str:
    for hi, name in _LABELS:
        if d < hi:
            return name
    return "Infeasible"


@dataclass
class Assessment:
    ssid: str
    bssid: str
    encryption: str
    difficulty: int
    label: str
    reasons: list = field(default_factory=list)
    attack: str = ""
    hashcat_cmd: str = ""
    recommend_cloud: bool = False


def _norm_enc(e: str) -> str:
    return (e or "wpa2").strip().lower().replace("/", "-")


def assess(target: dict) -> Assessment:
    ssid = target.get("ssid") or "<hidden>"
    bssid = target.get("bssid") or "00:00:00:00:00:00"
    enc = _norm_enc(target.get("encryption", "wpa2"))
    d = ENC_DIFFICULTY.get(enc, 55)
    reasons = []

    if target.get("wps"):
        d -= 15
        reasons.append("WPS enabled -> try Pixie-Dust / PIN before cracking")
    for prefix, why in DEFAULT_HINTS:
        if ssid.upper().startswith(prefix.upper()):
            d -= 10
            reasons.append(why)
            break
    if target.get("hidden"):
        d += 5
        reasons.append("hidden SSID (slightly harder to engage)")
    if target.get("clients", 0) > 0:
        reasons.append(f"{target['clients']} client(s) present -> easy handshake")
    else:
        reasons.append("no clients -> rely on PMKID (clientless)")

    d = max(0, min(100, d))
    bss = bssid.replace(":", "").lower()
    if enc == "open":
        attack, cmd = "No key needed - just associate.", ""
    elif enc == "wep":
        attack, cmd = "WEP: collect IVs, aircrack-ng.", f"aircrack-ng {bss}.cap"
    elif enc in ("wpa3", "wpa3-sae", "owe"):
        attack = "WPA3/SAE: wordlists don't apply; needs online/clientless or downgrade."
        cmd = ""
    elif enc == "wpa2-eap":
        attack = "WPA2-Enterprise: no PSK to crack; out of scope for rockyou."
        cmd = ""
    else:
        attack = "WPA/WPA2-PSK: capture handshake -> hashcat -m 22000 + rockyou."
        cmd = f"hashcat -m 22000 {bss}.hc22000 rockyou.txt"

    return Assessment(
        ssid=ssid, bssid=bssid, encryption=enc, difficulty=d, label=_label(d),
        reasons=reasons, attack=attack, hashcat_cmd=cmd,
        recommend_cloud=(d >= 60 and bool(cmd)),
    )
