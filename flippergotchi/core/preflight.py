"""Environment probing for the "doctor" preflight -- pure, side-effect-free.

Answers "what can this box actually do right now?" before the user tries to
capture or crack on real hardware: which CLI tools are installed, whether we're
privileged enough for monitor mode, whether the configured interface exists and
is wireless, whether the wordlist is present, and the WiFi regulatory domain.

Everything here is read-only. Every probe is guarded: a missing tool, no root,
no ``/sys`` (e.g. macOS/CI), an unreadable file -- all fold into a False/None/0
result, never an exception. Nothing is ever mutated (no monitor mode, no
interface bring-up); that belongs to :mod:`core.wifi.monitor`.

NEEDS ON-HARDWARE VALIDATION: the ``iw reg get`` parsing and the
``/sys/class/net/<iface>/wireless`` wireless-detection heuristic can only be
confirmed against the Flipper One's MT7921 radio.

Config fields read (all via getattr, defaults shown):
    interface  str  mon0                              -- capture interface
    wordlist   str  /usr/share/wordlists/rockyou.txt  -- hashcat wordlist
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess

log = logging.getLogger(__name__)

# Tools the active pipeline may shell out to. Presence is probed, never assumed.
TOOLS = (
    "hcxdumptool",      # capture (PMKID + EAPOL)
    "hcxpcapngtool",    # convert .pcapng -> hashcat 22000
    "hashcat",          # local crack
    "iw",               # regdomain + iface introspection / monitor mode
    "ip",               # iface up/down
    "rfkill",           # unblock radio
    "airmon-ng",        # monitor-mode helper (aircrack-ng suite)
    "aircrack-ng",      # legacy crack / capture validation
    "bettercap",        # alternate capture backend
    "gpsd",             # GPS for the fitness/geofence layer
)

CAP_NET_ADMIN_BIT = 12          # CapEff bit for CAP_NET_ADMIN


def check_tools() -> dict:
    """Map each known tool name -> True if it is on PATH."""
    return {name: shutil.which(name) is not None for name in TOOLS}


def check_privileges() -> dict:
    """Best-effort privilege probe (read-only).

    ``is_root``: euid 0. ``has_cap_net_admin``: euid 0, or CAP_NET_ADMIN set in
    /proc/self/status CapEff (so a capability-granted non-root user is detected
    too). ``can_monitor``: either of the above -- "privileged enough to try".
    """
    is_root = False
    try:
        if hasattr(os, "geteuid"):
            is_root = os.geteuid() == 0
    except OSError:                 # pragma: no cover - extremely unusual
        is_root = False

    has_cap = is_root
    if not has_cap:
        try:
            with open("/proc/self/status", "r", encoding="ascii",
                      errors="ignore") as fh:
                for line in fh:
                    if line.startswith("CapEff:"):
                        caps = int(line.split()[1], 16)
                        has_cap = bool(caps & (1 << CAP_NET_ADMIN_BIT))
                        break
        except (OSError, ValueError):
            has_cap = is_root
    return {
        "is_root": is_root,
        "has_cap_net_admin": has_cap,
        "can_monitor": bool(is_root or has_cap),
    }


def check_wordlist(cfg) -> dict:
    """Locate the hashcat wordlist and report its presence + size."""
    raw = getattr(cfg, "wordlist", "/usr/share/wordlists/rockyou.txt")
    path = os.path.expanduser(str(raw or ""))
    exists = False
    size = 0
    if path:
        try:
            exists = os.path.isfile(path)
            if exists:
                size = os.path.getsize(path)
        except OSError:
            exists, size = False, 0
    return {"path": path, "exists": exists, "size": size}


def check_interface(cfg) -> dict:
    """Report whether ``cfg.interface`` exists and looks wireless (read-only)."""
    iface = str(getattr(cfg, "interface", "mon0") or "")
    exists = False
    wireless = False
    if iface:
        base = "/sys/class/net/" + iface
        try:
            exists = os.path.isdir(base)
        except OSError:
            exists = False
        if exists:
            # A wireless netdev exposes a 'wireless' or 'phy80211' node.
            for marker in ("wireless", "phy80211"):
                try:
                    if os.path.exists(os.path.join(base, marker)):
                        wireless = True
                        break
                except OSError:
                    continue
    return {"name": iface, "exists": exists, "wireless": wireless}


def check_regdomain() -> dict:
    """Read the WiFi regulatory domain via ``iw reg get`` (best-effort)."""
    out = {"available": False, "country": None, "raw": ""}
    if shutil.which("iw") is None:
        return out
    try:
        proc = subprocess.run(
            ["iw", "reg", "get"],
            capture_output=True, text=True, timeout=6.0, check=False,
        )
    except (subprocess.SubprocessError, OSError) as exc:  # noqa: BLE001
        log.debug("iw reg get failed (%s)", exc)
        return out
    text = proc.stdout or ""
    out["raw"] = text
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("country "):
            # e.g. "country AU: DFS-ETSI" -> "AU"
            token = line[len("country "):].split(":", 1)[0].strip()
            if token:
                out["country"] = token
                out["available"] = True
                break
    return out


def preflight(cfg) -> dict:
    """Aggregate every probe into one structured, read-only report."""
    return {
        "tools": check_tools(),
        "privileges": check_privileges(),
        "interface": check_interface(cfg),
        "wordlist": check_wordlist(cfg),
        "regdomain": check_regdomain(),
    }
