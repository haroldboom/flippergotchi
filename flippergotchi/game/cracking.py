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
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from ..core import handshake as hs

log = logging.getLogger(__name__)


# -- stdlib multipart/form-data helper --------------------------------------
def _encode_multipart(field_name: str, filename: str, data: bytes,
                      extra_fields: dict | None = None):
    """Build a multipart/form-data body (one file + optional text fields).

    Returns (content_type, body_bytes). Pure stdlib so the cloud upload needs
    no third-party HTTP library."""
    boundary = "----flippergotchi" + str(int(time.time() * 1000))
    crlf = b"\r\n"
    out = []
    for k, v in (extra_fields or {}).items():
        out.append(b"--" + boundary.encode() + crlf)
        out.append(f'Content-Disposition: form-data; name="{k}"'.encode() + crlf + crlf)
        out.append(str(v).encode() + crlf)
    out.append(b"--" + boundary.encode() + crlf)
    out.append(
        f'Content-Disposition: form-data; name="{field_name}"; '
        f'filename="{os.path.basename(filename)}"'.encode() + crlf)
    out.append(b"Content-Type: application/octet-stream" + crlf + crlf)
    out.append(data + crlf)
    out.append(b"--" + boundary.encode() + b"--" + crlf)
    return "multipart/form-data; boundary=" + boundary, b"".join(out)


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
        # Dry-run takes precedence over everything (incl. the sim shortcut): it
        # validates the capture and shows the planned hashcat command WITHOUT
        # running it, so the pipeline can be exercised on real hardware without
        # burning a crack. Works even if hashcat isn't installed.
        if bool(getattr(self.cfg, "dry_run", False)):
            return self._crack_dry(monster, handshake_path)
        if self.sim or not handshake_path or not os.path.exists(handshake_path):
            return self._sim(monster)
        try:
            return self._crack_real(monster, handshake_path)
        except Exception:  # noqa: BLE001 - never raise out of a crack attempt
            log.debug("real crack path failed; falling back to sim", exc_info=True)
            return self._sim(monster)

    # -- dry-run path ----------------------------------------------------- #
    def _crack_dry(self, monster, handshake_path: str | None) -> CrackResult:
        """Validate the capture and report the hashcat command we WOULD run,
        without executing it. Never touches hashcat; capture validation is the
        pure-python parser in ``core.handshake`` so this works tool-free."""
        if not handshake_path or not os.path.exists(handshake_path):
            return CrackResult(result="dry-run", via="dry-run", mode="",
                               detail="DRY-RUN: no capture file to inspect "
                                      "(nothing to crack)")
        info = hs.analyze_capture(handshake_path)
        cap = os.path.basename(handshake_path)
        if not info.is_crackable:
            return CrackResult(
                result="dry-run", via="dry-run", mode="",
                detail=f"DRY-RUN: {cap} has no PMKID or complete 4-way handshake "
                       "-- would NOT crack")
        mode = "pmkid" if (info.contains_pmkid and not info.has_complete_4way) \
            else "handshake"
        hashcat = shutil.which(getattr(self.cfg, "hashcat_bin", "hashcat")) \
            or str(getattr(self.cfg, "hashcat_bin", "hashcat"))
        wordlists = self._wordlists() or ["<wordlist>"]
        rules = getattr(self.cfg, "hashcat_rules", "") or ""
        cmd = [hashcat, "-m", "22000", "<capture.hc22000>", *wordlists,
               "--potfile-disable", "-o", "<out>", "--quiet"]
        if rules:
            cmd += ["-r", rules]
        plan = " ".join(cmd)
        log.info("DRY-RUN crack (%s): %s", mode, plan)
        return CrackResult(result="dry-run", via="dry-run", mode=mode,
                           detail=f"DRY-RUN {mode}: valid capture; would run: {plan}")

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
    """Distributed/online WPA cracking: upload a capture, poll later for the PSK.

    Two services:
      * **wpa-sec** (https://wpa-sec.stanev.org) -- the validated path. Uploads
        the .pcap/.pcapng with your account "key" cookie; recovered keys are
        downloaded later from the same account (``?api&dl=1``).
      * **onlinehashcrack** -- a generic multipart upload to a configurable
        endpoint (their API has shifted over time; NEEDS VALIDATION).

    Cracking is asynchronous: ``submit`` returns "submitted" once the capture is
    accepted; ``fetch_results`` later returns recovered ``{BSSID: psk}``.

    Safety: uploading a capture to a third party is an outward-facing action, so
    ``submit`` is suppressed under ``cfg.dry_run`` (reports what it would do) and
    in ``cfg.simulate`` (returns a simulated escalation -- no network). Nothing
    here raises; network/HTTP errors degrade to a "failed" CrackResult.
    """

    def __init__(self, cfg):
        self.cfg = cfg
        self.service = str(getattr(cfg, "cloud_service", "wpa-sec") or "wpa-sec")

    # -- submit ----------------------------------------------------------- #
    def submit(self, monster, handshake_path: str | None = None) -> CrackResult:
        # capture path can come from the arg or be stored on the monster.
        path = handshake_path or getattr(monster, "capture_path", "") or ""

        if bool(getattr(self.cfg, "dry_run", False)):
            where = path or "<captured handshake>"
            return CrackResult(result="dry-run", via=self.service, mode="cloud",
                               detail=f"DRY-RUN: would upload {os.path.basename(where)} "
                                      f"to {self.service}")
        if bool(getattr(self.cfg, "simulate", False)):
            # No real network in sim; preserve the game's "escalate" outcome.
            return CrackResult(result="submitted", via=self.service, mode="cloud",
                               detail=f"simulated upload to {self.service}")
        if not path or not os.path.exists(path):
            return CrackResult(result="failed", via=self.service, mode="cloud",
                               detail="no capture file to upload")
        try:
            if self.service == "onlinehashcrack":
                return self._submit_onlinehashcrack(path)
            return self._submit_wpa_sec(path)
        except Exception as exc:  # noqa: BLE001 - never raise out of a submit
            log.warning("cloud submit to %s failed (%s)", self.service, exc)
            return CrackResult(result="failed", via=self.service, mode="cloud",
                               detail=f"upload error: {exc}")

    def _submit_wpa_sec(self, path: str) -> CrackResult:
        """POST the capture to wpa-sec. NEEDS ON-HARDWARE VALIDATION."""
        key = str(getattr(self.cfg, "wpa_sec_key", "") or "")
        if not key:
            return CrackResult(result="failed", via="wpa-sec", mode="cloud",
                               detail="set cfg.wpa_sec_key (your wpa-sec API key)")
        base = str(getattr(self.cfg, "wpa_sec_url", "https://wpa-sec.stanev.org/"))
        url = base.rstrip("/") + "/?api&upload"
        with open(path, "rb") as fh:
            data = fh.read()
        ctype, body = _encode_multipart("file", path, data)
        text = self._http(url, body=body,
                          headers={"Content-Type": ctype, "Cookie": f"key={key}"})
        low = (text or "").lower()
        if "already" in low:
            return CrackResult(result="submitted", via="wpa-sec", mode="cloud",
                               detail="already submitted to wpa-sec; awaiting result")
        if "error" in low or "denied" in low:
            return CrackResult(result="failed", via="wpa-sec", mode="cloud",
                               detail=f"wpa-sec rejected upload: {text.strip()[:120]}")
        return CrackResult(result="submitted", via="wpa-sec", mode="cloud",
                           detail="uploaded to wpa-sec; run `cloud results` later")

    def _submit_onlinehashcrack(self, path: str) -> CrackResult:
        """Generic multipart upload to a configurable OHC endpoint. NEEDS
        VALIDATION against the live onlinehashcrack API."""
        url = str(getattr(self.cfg, "onlinehashcrack_url", "") or "")
        if not url:
            return CrackResult(result="failed", via="onlinehashcrack", mode="cloud",
                               detail="set cfg.onlinehashcrack_url")
        key = str(getattr(self.cfg, "onlinehashcrack_key", "") or "")
        with open(path, "rb") as fh:
            data = fh.read()
        fields = {"api_key": key} if key else None
        ctype, body = _encode_multipart("file", path, data, extra_fields=fields)
        text = self._http(url, body=body, headers={"Content-Type": ctype})
        return CrackResult(result="submitted", via="onlinehashcrack", mode="cloud",
                           detail=f"uploaded to onlinehashcrack ({text.strip()[:80]})")

    # -- fetch results ---------------------------------------------------- #
    def fetch_results(self) -> dict:
        """Return recovered ``{BSSID(upper, colon-separated): psk}`` from the
        cloud account. wpa-sec only; never raises (returns {} on any error)."""
        if bool(getattr(self.cfg, "simulate", False)) or \
                bool(getattr(self.cfg, "dry_run", False)):
            return {}
        if self.service != "wpa-sec":
            log.info("fetch_results only supports wpa-sec (service=%s)", self.service)
            return {}
        key = str(getattr(self.cfg, "wpa_sec_key", "") or "")
        if not key:
            return {}
        try:
            base = str(getattr(self.cfg, "wpa_sec_url", "https://wpa-sec.stanev.org/"))
            url = base.rstrip("/") + "/?api&dl=1"
            text = self._http(url, headers={"Cookie": f"key={key}"})
            return _parse_wpa_sec_potfile(text or "")
        except Exception as exc:  # noqa: BLE001
            log.warning("wpa-sec result fetch failed (%s)", exc)
            return {}

    # -- http ------------------------------------------------------------- #
    def _http(self, url: str, body: bytes | None = None,
              headers: dict | None = None) -> str:
        timeout = float(getattr(self.cfg, "cloud_timeout", 30) or 30)
        req = urllib.request.Request(
            url, data=body, headers=headers or {},
            method="POST" if body is not None else "GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.read().decode("utf-8", errors="replace")


def _parse_wpa_sec_potfile(text: str) -> dict:
    """Parse wpa-sec's downloaded results into ``{BSSID: psk}``.

    wpa-sec returns lines like ``<apmac>:<stamac>:<essid>:<psk>`` where the MACs
    are 12 hex chars (no separators). We normalise the AP MAC to the project's
    ``AA:BB:CC:DD:EE:FF`` form and take the last field as the PSK."""
    out: dict = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or ":" not in line:
            continue
        parts = line.split(":")
        if len(parts) < 4:
            continue
        mac, psk = parts[0].strip(), parts[-1]
        if not psk:
            continue
        bssid = _fmt_mac(mac)
        if bssid:
            out[bssid] = psk
    return out


def _fmt_mac(mac: str) -> str:
    """12 hex chars (wpa-sec) or already-colonised -> AA:BB:CC:DD:EE:FF."""
    h = mac.replace(":", "").replace("-", "").strip().upper()
    if len(h) != 12 or any(c not in "0123456789ABCDEF" for c in h):
        return ""
    return ":".join(h[i:i + 2] for i in range(0, 12, 2))
