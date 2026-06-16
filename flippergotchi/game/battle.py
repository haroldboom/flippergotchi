"""Battling a captured monster = trying to crack its handshake.

Flow:  validate capture  ->  local hashcat + wordlists  ->  (if it fails &
you allow it)  cloud crack.

Authorization: cracking is only allowed against networks you own / are cleared
to test. A monster is "in your dojo" if its SSID/BSSID matches cfg.home_networks
(or you pass force_authorized for a one-off you've confirmed). Otherwise battle()
refuses. Collecting/scanning monsters is always fine; only the *crack* is gated.

The actual crack pipeline lives in ``game/cracking.py`` (validate -> convert ->
hashcat -> parse, with a no-hardware simulator). This module owns the
authorization gate and the game wiring, and returns the legacy result dict
{"result","via","key", ...} so existing callers/tests keep working.
"""
from __future__ import annotations

from .analysis import assess
from .cracking import CloudCracker, CrackResult, LocalCracker

__all__ = ["is_authorized", "battle", "LocalCracker", "CloudCracker", "CrackResult"]


def is_authorized(monster, cfg) -> bool:
    home = getattr(cfg, "home_networks", []) or []
    if isinstance(home, str):          # defensive: never iterate a string's chars
        home = [home]
    needles = [str(n).lower() for n in home if n]
    hay = f"{monster.name} {monster.id}".lower()
    return any(n in hay for n in needles)


def battle(monster, cfg, handshake_path: str | None = None,
           force_authorized: bool = False) -> dict:
    if monster.kind == "ble":
        monster.defeated = True
        return {"result": "tamed", "via": "scan",
                "key": "", "note": "BLE creatures are tamed by scanning, not cracked"}
    if not (force_authorized or is_authorized(monster, cfg)):
        return {"result": "refused", "via": "-", "key": "",
                "note": "not in your authorized dojo (cfg.home_networks)"}

    res: CrackResult = LocalCracker(cfg).crack(monster, handshake_path)
    if res.result == "failed" and assess(monster.__dict__).recommend_cloud \
            and getattr(cfg, "cloud_enabled", False):
        res = CloudCracker(cfg).submit(monster, handshake_path)

    if res.result == "cracked":
        monster.defeated = True
        monster.key = res.key
    return res.to_dict()
