"""Passive AP/client discovery for the native WiFi stack.

Passive scanning collects nothing but beacons/probe responses the radio already
hears, so it requires NO authorization. The primary path parses ``iw dev <if>
scan``; an airodump-ng CSV reader is provided for the capture loop (hcxdumptool
and airodump both emit CSVs we can mine for live AP/client lists).

Every AP is normalised to the project's canonical dict shape, identical to
``core.bettercap._translate_ap``:

    {"bssid","ssid","encryption","band","wps","clients","signal"}

with ``encryption`` in {open, wep, wpa, wpa2}. WPA3/SAE, Enterprise (EAP) and
OWE are skipped (not wordlist-crackable, so never surfaced as monsters).

NEEDS ON-HARDWARE VALIDATION: exact ``iw scan`` field formatting varies by iw
version and driver, so the parser is defensive and tolerant of missing fields.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess

# Reuse the project's band derivation + crackable set so behaviour matches the
# bettercap path exactly.
from ..bettercap import CRACKABLE, _band_from_channel

log = logging.getLogger(__name__)


def _freq_to_band_channel(mhz: int):
    """Map a frequency in MHz to (band, channel). Covers 2.4/5/6GHz."""
    try:
        f = int(mhz)
    except (TypeError, ValueError):
        return ("2.4GHz", None)
    if 2412 <= f <= 2484:
        ch = 14 if f == 2484 else (f - 2407) // 5
        return ("2.4GHz", ch)
    if 5160 <= f <= 5885:
        return ("5GHz", (f - 5000) // 5)
    if 5955 <= f <= 7115:
        # 6GHz: ch = (f - 5950) / 5
        return ("6GHz", (f - 5950) // 5)
    return ("2.4GHz", None)


def _norm_encryption_from_flags(rsn: bool, wpa: bool, wep: bool,
                                sae: bool, eap: bool, owe: bool) -> str | None:
    """Collapse parsed security flags into the project's encryption label.

    Returns None for schemes we deliberately skip (WPA3/SAE, Enterprise, OWE).
    """
    if sae or owe or eap:
        return None  # wpa3 / owe / enterprise -> not surfaced
    if rsn:
        return "wpa2"
    if wpa:
        return "wpa"
    if wep:
        return "wep"
    return "open"


def parse_iw_scan(text: str) -> list:
    """Parse ``iw dev <if> scan`` output into canonical AP dicts.

    Skips encryptions outside the crackable set. Never raises.
    """
    aps: list = []
    if not text:
        return aps

    # Split into per-BSS blocks. Each starts with "BSS aa:bb:..".
    blocks = re.split(r"(?m)^BSS\s+", text)
    for blk in blocks:
        blk = blk.strip()
        if not blk:
            continue
        try:
            ap = _parse_iw_bss(blk)
        except Exception as exc:  # noqa: BLE001 - one bad block must not kill the scan
            log.debug("iw scan block parse failed (%s)", exc)
            ap = None
        if ap is not None:
            aps.append(ap)
    return aps


def _parse_iw_bss(blk: str) -> dict | None:
    # BSSID is the first token of the block (already split off "BSS ").
    m = re.match(r"([0-9a-fA-F:]{17})", blk)
    if not m:
        return None
    bssid = m.group(1).upper()

    ssid = ""
    ms = re.search(r"(?m)^\s*SSID:\s*(.*)$", blk)
    if ms:
        ssid = ms.group(1).rstrip()

    signal = -60
    msig = re.search(r"signal:\s*(-?\d+(?:\.\d+)?)\s*dBm", blk)
    if msig:
        try:
            signal = int(float(msig.group(1)))
        except ValueError:
            pass

    band = "2.4GHz"
    channel = None
    mfreq = re.search(r"freq:\s*(\d+)", blk)
    if mfreq:
        band, channel = _freq_to_band_channel(mfreq.group(1))
    mch = re.search(r"(?m)\*?\s*(?:primary channel|DS Parameter set: channel):\s*(\d+)", blk)
    if mch:
        try:
            channel = int(mch.group(1))
            band = _band_from_channel(channel)
        except ValueError:
            pass

    low = blk.lower()
    rsn = "rsn:" in low
    wpa = "wpa:" in low
    # SAE (WPA3) / OWE / EAP are detected via the AKM suite text iw prints.
    sae = "sae" in low or "wpa3" in low
    owe = "owe" in low
    # Only flag enterprise if an explicit 802.1X AKM is named.
    eap = ("ieee 802.1x" in low) or ("8021x" in low)
    # WEP: privacy bit set but no RSN/WPA IE.
    privacy = "privacy" in low
    wep = privacy and not rsn and not wpa

    encryption = _norm_encryption_from_flags(rsn, wpa, wep, sae, eap, owe)
    if encryption is None or encryption not in CRACKABLE:
        return None

    wps = "wps:" in low or "wi-fi protected setup" in low

    return {
        "bssid": bssid,
        "ssid": str(ssid),
        "encryption": encryption,
        "band": band,
        "wps": bool(wps),
        "clients": 0,           # iw scan sees APs, not associated clients
        "signal": signal,
    }


def scan_iw(iface: str, timeout: float = 12.0) -> list:
    """Run ``iw dev <iface> scan`` and return canonical AP dicts.

    Requires CAP_NET_ADMIN for an active scan request, but the *frames* it
    collects are passive beacons, so no RF is injected at a target. Returns []
    on any failure (tool missing, no permission, timeout). Never raises.

    NEEDS ON-HARDWARE VALIDATION.
    """
    if not iface or shutil.which("iw") is None:
        return []
    try:
        proc = subprocess.run(
            ["iw", "dev", iface, "scan"],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except (subprocess.SubprocessError, OSError) as exc:  # noqa: BLE001
        log.warning("iw scan on %s failed (%s); no detections", iface, exc)
        return []
    if proc.returncode != 0:
        log.debug("iw scan on %s returned %s: %s", iface, proc.returncode,
                  (proc.stderr or "").strip()[:200])
        return []
    return parse_iw_scan(proc.stdout)


# -- airodump-ng / hcxdumptool CSV ------------------------------------------
#
# airodump writes a CSV with two sections: APs, then a blank line, then
# "Station MAC" rows. We mine the AP section and count associated stations per
# BSSID for the 'clients' field. hcxdumptool can emit a compatible CSV too.

def parse_airodump_csv(text: str) -> list:
    """Parse an airodump-ng CSV into canonical AP dicts. Never raises."""
    if not text:
        return []
    lines = text.splitlines()

    # Find the AP header and the Station header (sections split by a blank line).
    ap_rows: list = []
    sta_rows: list = []
    section = None
    for raw in lines:
        line = raw.strip()
        low = line.lower()
        if low.startswith("bssid,") or low.startswith("bssid ,"):
            section = "ap"
            continue
        if low.startswith("station mac"):
            section = "sta"
            continue
        if not line:
            continue
        if section == "ap":
            ap_rows.append(raw)
        elif section == "sta":
            sta_rows.append(raw)

    # Count clients per AP BSSID from the station section (column 6 = AP BSSID).
    client_counts: dict = {}
    for row in sta_rows:
        cols = [c.strip() for c in row.split(",")]
        if len(cols) < 6:
            continue
        ap_bssid = cols[5].upper()
        if re.fullmatch(r"[0-9A-F:]{17}", ap_bssid):
            client_counts[ap_bssid] = client_counts.get(ap_bssid, 0) + 1

    out: list = []
    for row in ap_rows:
        try:
            ap = _parse_airodump_ap_row(row, client_counts)
        except Exception as exc:  # noqa: BLE001
            log.debug("airodump row parse failed (%s)", exc)
            ap = None
        if ap is not None:
            out.append(ap)
    return out


def _parse_airodump_ap_row(row: str, client_counts: dict) -> dict | None:
    # airodump AP columns:
    # 0 BSSID, 1 First seen, 2 Last seen, 3 channel, 4 Speed, 5 Privacy,
    # 6 Cipher, 7 Auth, 8 Power, ... 13 ESSID (last meaningful field)
    cols = [c.strip() for c in row.split(",")]
    if len(cols) < 9:
        return None
    bssid = cols[0].upper()
    if not re.fullmatch(r"[0-9A-F:]{17}", bssid):
        return None

    try:
        channel = int(cols[3])
    except (ValueError, IndexError):
        channel = 0
    band = _band_from_channel(channel)

    privacy = cols[5].upper()
    auth = cols[7].upper() if len(cols) > 7 else ""
    encryption = _norm_airodump_privacy(privacy, auth)
    if encryption is None or encryption not in CRACKABLE:
        return None

    signal = -60
    try:
        signal = int(cols[8])
    except (ValueError, IndexError):
        pass

    # ESSID is the final column; airodump pads with trailing fields.
    ssid = cols[13] if len(cols) > 13 else (cols[-1] if cols else "")

    return {
        "bssid": bssid,
        "ssid": str(ssid),
        "encryption": encryption,
        "band": band,
        "wps": False,             # airodump CSV doesn't carry WPS state
        "clients": int(client_counts.get(bssid, 0)),
        "signal": signal,
    }


def _norm_airodump_privacy(privacy: str, auth: str) -> str | None:
    """Map airodump's Privacy/Auth columns to a project encryption label."""
    p = (privacy or "").upper()
    a = (auth or "").upper()
    if "MGT" in p or "MGT" in a or "EAP" in a:
        return None  # enterprise
    if "SAE" in p or "WPA3" in p or "SAE" in a:
        return None  # wpa3
    if "OWE" in p:
        return None
    if "WPA2" in p:
        return "wpa2"
    if "WPA" in p:
        return "wpa"
    if "WEP" in p:
        return "wep"
    if not p or "OPN" in p:
        return "open"
    return None


def read_airodump_csv(path: str) -> list:
    """Read an airodump/hcxdumptool CSV file into AP dicts. Never raises."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            return parse_airodump_csv(fh.read())
    except OSError as exc:
        log.debug("could not read airodump csv %s (%s)", path, exc)
        return []
