"""Battling a captured monster = trying to crack its handshake.

Flow:  local hashcat + rockyou  ->  (if it fails & you allow it)  cloud crack.

Authorization: cracking is only allowed against networks you own / are cleared
to test. A monster is "in your dojo" if its SSID/BSSID matches cfg.home_networks
(or you pass force_authorized for a one-off you've confirmed). Otherwise battle()
refuses. Collecting/scanning monsters is always fine; only the *crack* is gated.
"""
from __future__ import annotations

import os
import random
import shutil

from .analysis import assess


def is_authorized(monster, cfg) -> bool:
    home = getattr(cfg, "home_networks", []) or []
    if isinstance(home, str):          # defensive: never iterate a string's chars
        home = [home]
    needles = [str(n).lower() for n in home if n]
    hay = f"{monster.name} {monster.id}".lower()
    return any(n in hay for n in needles)


class LocalCracker:
    """hashcat -m 22000 against rockyou. Real on hardware; simulated otherwise."""

    name = "local-hashcat"

    def __init__(self, cfg):
        self.cfg = cfg
        self.sim = cfg.simulate or not shutil.which(getattr(cfg, "hashcat_bin", "hashcat"))

    def crack(self, monster, handshake_path: str | None = None) -> dict:
        if self.sim or not handshake_path or not os.path.exists(handshake_path):
            return self._sim(monster)
        # TODO (hardware): convert capture -> .hc22000 with hcxpcapngtool, then:
        #   hashcat -m 22000 <file>.hc22000 <wordlist> --potfile-disable -o found
        # parse the cracked PSK from stdout/outfile and return it here.
        return self._sim(monster)

    def _sim(self, monster) -> dict:
        # weaker defense => higher chance rockyou lands the key
        p = max(0.02, min(0.97, 1.0 - monster.defense / 100.0))
        if random.random() < p:
            key = random.choice(
                ["password123", "hunter2!", f"{monster.name.lower()}2024",
                 "letmein99", "qwerty12345", "sunshine1"]
            )
            return {"result": "cracked", "via": "local rockyou", "key": key}
        return {"result": "failed", "via": "local rockyou", "key": ""}


class CloudCracker:
    """Distributed/online cracking fallback. Two supported services."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.service = getattr(cfg, "cloud_service", "wpa-sec")

    def submit(self, monster, handshake_path: str | None = None) -> dict:
        # TODO (hardware): actually upload the capture.
        #   wpa-sec:         POST .pcap to https://wpa-sec.stanev.org/?api with your key
        #   onlinehashcrack: POST .hc22000/.pcap to their submission endpoint
        # Both return async; you poll later for the recovered PSK.
        return {"result": "submitted", "via": self.service,
                "key": "", "note": f"uploaded to {self.service}; check back later"}


def battle(monster, cfg, handshake_path: str | None = None,
           force_authorized: bool = False) -> dict:
    if monster.kind == "ble":
        monster.defeated = True
        return {"result": "tamed", "via": "scan",
                "key": "", "note": "BLE creatures are tamed by scanning, not cracked"}
    if monster.encryption in ("wpa3", "wpa3-sae", "owe", "wpa2-eap"):
        return {"result": "immune", "via": "-", "key": "",
                "note": f"{monster.encryption} can't be beaten with a wordlist"}
    if not (force_authorized or is_authorized(monster, cfg)):
        return {"result": "refused", "via": "-", "key": "",
                "note": "not in your authorized dojo (cfg.home_networks)"}

    res = LocalCracker(cfg).crack(monster, handshake_path)
    if res["result"] == "failed" and assess(monster.__dict__).recommend_cloud \
            and getattr(cfg, "cloud_enabled", False):
        res = CloudCracker(cfg).submit(monster, handshake_path)

    if res["result"] == "cracked":
        monster.defeated = True
        monster.key = res["key"]
    return res
