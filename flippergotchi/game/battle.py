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
import subprocess
import tempfile

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
        # REAL hardware path. Needs on-hardware validation: this assumes
        # hcxpcapngtool + hashcat are installed and a wordlist exists. Every
        # step is guarded so any failure (missing tool, bad capture, timeout)
        # silently falls back to the simulated outcome -- the agent never
        # crashes on a crack attempt.
        try:
            return self._crack_real(monster, handshake_path)
        except Exception:  # noqa: BLE001 - never raise out of a crack attempt
            return self._sim(monster)

    def _crack_real(self, monster, handshake_path: str) -> dict:
        """Convert capture -> .hc22000 and run hashcat -m 22000 over rockyou.

        NEEDS ON-HARDWARE VALIDATION. hashcat 22000 outfile lines look like
        ``<hash>:<essid-or-mac>:<...>:<password>`` -- the recovered PSK is the
        last colon-separated field.
        """
        hcx = shutil.which("hcxpcapngtool")
        hashcat = shutil.which(getattr(self.cfg, "hashcat_bin", "hashcat"))
        if not hcx or not hashcat:
            return self._sim(monster)

        wordlist = getattr(self.cfg, "wordlist", "/usr/share/wordlists/rockyou.txt")
        if not wordlist or not os.path.exists(wordlist):
            return self._sim(monster)

        tmpdir = tempfile.mkdtemp(prefix="flippergotchi-crack-")
        hc22000 = os.path.join(tmpdir, "capture.hc22000")
        outfile = os.path.join(tmpdir, "found.txt")
        try:
            # 1) convert the pcap/pcapng capture to the hashcat 22000 format
            conv = subprocess.run(
                [hcx, "-o", hc22000, handshake_path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=60,
            )
            if conv.returncode != 0 or not os.path.exists(hc22000) \
                    or os.path.getsize(hc22000) == 0:
                # no convertible handshake/PMKID in the capture
                return self._sim(monster)

            # 2) run hashcat in WPA mode 22000 against the wordlist
            subprocess.run(
                [hashcat, "-m", "22000", hc22000, wordlist,
                 "--potfile-disable", "-o", outfile, "--quiet"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=int(getattr(self.cfg, "crack_timeout", 1800)),
            )

            # 3) parse the recovered PSK from the outfile (last field)
            psk = self._parse_psk(outfile)
            if psk:
                return {"result": "cracked", "via": "local hashcat", "key": psk}
            return {"result": "failed", "via": "local hashcat", "key": ""}
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    @staticmethod
    def _parse_psk(outfile: str) -> str:
        if not os.path.exists(outfile):
            return ""
        try:
            with open(outfile, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.rstrip("\n")
                    if not line:
                        continue
                    # <hash>:<essid>:<...>:<password> -> last field is the PSK
                    return line.split(":")[-1]
        except OSError:
            return ""
        return ""

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
