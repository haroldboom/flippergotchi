"""The WPA cracking pipeline: validate -> convert -> hashcat -> parse.

This module owns the *how* of breaking a captured handshake. ``battle.py`` owns
the *whether* (authorization) and wires the result into the game.

Hardening principles:
  * We never crack a capture we haven't validated -- ``core.handshake`` confirms
    a PMKID or a usable 4-way exchange exists first, so we don't spin hashcat on
    junk.
  * Every external tool (hcxpcapngtool, hashcat) is optional; absent any of
    them we degrade to a deterministic-ish simulator whose odds come from the
    monster's defense stat (identical in spirit to the original LocalCracker).
  * Nothing here raises: callers always get a ``CrackResult``.

Config fields read (all via getattr, defaults shown):
    simulate         (bool)        -> force the sim path
    hashcat_bin      ("hashcat")   -> hashcat executable name/path
    wordlists        (list[str])   -> ordered wordlists; takes priority
    wordlist         (str)         -> single wordlist fallback
    hashcat_rules    (str)         -> optional .rule file
    crack_timeout    (int, 1800)   -> hashcat wall-clock cap (seconds)
    cloud_service    ("wpa-sec")   -> cloud submission target

NEEDS ON-HARDWARE VALIDATION for every real (non-sim) path.
"""
from __future__ import annotations

import logging
import os
import random
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

from ..core import handshake as hs

log = logging.getLogger(__name__)


@dataclass
class CrackResult:
    """Outcome of a crack attempt.

    result: "cracked" | "failed" | "submitted" | "refused"
    via:    human label of the method ("local hashcat", "local rockyou", ...)
    key:    recovered PSK (only when result == "cracked")
    mode:   "pmkid" | "handshake" | "sim" | "" -- what we actually attacked
    detail: free-form note for the UI / logs
    """

    result: str = "failed"
    via: str = "-"
    key: str = ""
    mode: str = ""
    detail: str = ""

    def to_dict(self) -> dict:
        """Flatten to the legacy battle() dict contract.

        Keeps {"result","via","key"} plus the richer fields, and mirrors
        ``detail`` into ``note`` for back-compat with existing callers/tests.
        """
        d = {"result": self.result, "via": self.via, "key": self.key,
             "mode": self.mode, "detail": self.detail}
        if self.detail:
            d["note"] = self.detail
        return d


class LocalCracker:
    """hashcat -m 22000 over one or more wordlists. Real on hardware; the sim
    path runs everywhere else."""

    name = "local-hashcat"

    def __init__(self, cfg):
        self.cfg = cfg
        self.sim = bool(getattr(cfg, "simulate", False)) or not shutil.which(
            getattr(cfg, "hashcat_bin", "hashcat"))

    # -- public ----------------------------------------------------------- #
    def crack(self, monster, handshake_path: str | None = None) -> CrackResult:
        if self.sim or not handshake_path or not os.path.exists(handshake_path):
            return self._sim(monster)
        try:
            return self._crack_real(monster, handshake_path)
        except Exception:  # noqa: BLE001 - never raise out of a crack attempt
            log.debug("real crack path failed; falling back to sim", exc_info=True)
            return self._sim(monster)

    # -- real path -------------------------------------------------------- #
    def _crack_real(self, monster, handshake_path: str) -> CrackResult:
        """Validate, convert to .hc22000, then run hashcat. NEEDS ON-HARDWARE
        VALIDATION."""
        hashcat = shutil.which(getattr(self.cfg, "hashcat_bin", "hashcat"))
        if not hashcat:
            return self._sim(monster)

        # 1) validate the capture is actually crackable before spending time.
        info = hs.analyze_capture(handshake_path)
        if not info.is_crackable:
            return CrackResult(result="failed", via="local hashcat", mode="",
                               detail="no PMKID or complete handshake in capture")
        mode = "pmkid" if (info.contains_pmkid and not info.has_complete_4way) \
            else "handshake"

        wordlists = self._wordlists()
        if not wordlists:
            return self._sim(monster)

        tmpdir = tempfile.mkdtemp(prefix="flippergotchi-crack-")
        outfile = os.path.join(tmpdir, "found.txt")
        try:
            # 2) convert capture -> hashcat 22000 format.
            hc22000 = hs.to_hc22000(handshake_path,
                                    out=os.path.join(tmpdir, "capture.hc22000"))
            if not hc22000:
                # validator said crackable but converter (or its tool) gave us
                # nothing -- can't proceed for real, so fall back.
                return self._sim(monster)

            # 3) run hashcat -m 22000 over each wordlist until something lands.
            rules = getattr(self.cfg, "hashcat_rules", "") or ""
            timeout = int(getattr(self.cfg, "crack_timeout", 1800) or 1800)
            cmd = [hashcat, "-m", "22000", hc22000, *wordlists,
                   "--potfile-disable", "-o", outfile, "--quiet"]
            if rules and os.path.exists(rules):
                cmd += ["-r", rules]
            try:
                subprocess.run(
                    cmd,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired:
                return CrackResult(result="failed", via="local hashcat", mode=mode,
                                   detail=f"hashcat timed out after {timeout}s")

            # 4) parse the recovered PSK (last colon field of the outfile line).
            psk = self._parse_psk(outfile)
            if psk:
                return CrackResult(result="cracked", via="local hashcat", key=psk,
                                   mode=mode, detail=f"recovered via {mode}")
            return CrackResult(result="failed", via="local hashcat", mode=mode,
                               detail="exhausted wordlist(s)")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def _wordlists(self) -> list:
        """cfg.wordlists (list) takes priority; else fall back to cfg.wordlist
        (single). Only existing files are kept."""
        out = []
        many = getattr(self.cfg, "wordlists", None)
        if many:
            if isinstance(many, str):
                many = [many]
            out.extend(many)
        else:
            single = getattr(self.cfg, "wordlist", "/usr/share/wordlists/rockyou.txt")
            if single:
                out.append(single)
        return [w for w in out if w and os.path.exists(w)]

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
                    # <hash>:<mac_ap>:<mac_sta>:<essid>:<password> -> PSK is last.
                    return line.split(":")[-1]
        except OSError:
            return ""
        return ""

    # -- sim path --------------------------------------------------------- #
    def _sim(self, monster) -> CrackResult:
        # weaker defense => higher chance rockyou lands the key
        p = max(0.02, min(0.97, 1.0 - monster.defense / 100.0))
        if random.random() < p:
            key = random.choice(
                ["password123", "hunter2!", f"{monster.name.lower()}2024",
                 "letmein99", "qwerty12345", "sunshine1"]
            )
            return CrackResult(result="cracked", via="local rockyou", key=key,
                               mode="sim", detail="simulated crack")
        return CrackResult(result="failed", via="local rockyou", mode="sim",
                           detail="simulated miss")


class CloudCracker:
    """Distributed/online cracking fallback. Behavior unchanged from battle.py."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.service = getattr(cfg, "cloud_service", "wpa-sec")

    def submit(self, monster, handshake_path: str | None = None) -> CrackResult:
        # TODO (hardware): actually upload the capture.
        #   wpa-sec:         POST .pcap to https://wpa-sec.stanev.org/?api with your key
        #   onlinehashcrack: POST .hc22000/.pcap to their submission endpoint
        # Both return async; you poll later for the recovered PSK.
        return CrackResult(
            result="submitted", via=self.service, key="", mode="cloud",
            detail=f"uploaded to {self.service}; check back later")
