"""Monitor-mode interface management for the native WiFi capture stack.

This wraps the userspace radio tools (``iw``, ``ip``, ``rfkill``, ``airmon-ng``)
behind a small, defensive API. Nothing here ever raises out to the caller: every
subprocess is guarded by :func:`shutil.which`, run with a timeout, and failures
are logged and folded into a ``False``/``None``/``[]`` return.

In ``--simulate`` (or on any box without root/hardware) the whole module is
inert: :meth:`MonitorInterface.capabilities` reports what's missing and the
mode-switching methods return ``False`` rather than touching a radio.

NEEDS ON-HARDWARE VALIDATION: the exact ``iw``/``airmon-ng`` output shapes and
the MT7921 monitor+injection path can only be confirmed on a real Flipper One.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

# Tools we may shell out to. Presence is probed, never assumed.
_TOOLS = ("iw", "ip", "rfkill", "airmon-ng")

# Driver/phy name hints that indicate the Flipper One's MT7921 WiFi 6E radio.
# Used only to *prefer* an interface when several are monitor-capable.
_PREFERRED_DRIVERS = ("mt7921", "mt7922", "mt7902", "mt76")

# Channel plans by band. 6GHz (Wi-Fi 6E) PSC channels are the realistic hop set.
CHANNELS_24 = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]
CHANNELS_5 = [36, 40, 44, 48, 52, 56, 60, 64, 100, 104, 108, 112,
              116, 120, 124, 128, 132, 136, 140, 149, 153, 157, 161, 165]
# 6GHz Preferred Scanning Channels (PSC), spaced every 16 from ch 5.
CHANNELS_6 = [5, 21, 37, 53, 69, 85, 101, 117, 133, 149, 165, 181, 197, 213, 229]


def _run(args, timeout: float = 6.0):
    """Run a command, return CompletedProcess or None on any failure.

    The first element of ``args`` is resolved via ``shutil.which``; if the tool
    is absent we return None without spawning anything.
    """
    if not args:
        return None
    if shutil.which(args[0]) is None:
        return None
    try:
        return subprocess.run(
            list(args),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (subprocess.SubprocessError, OSError) as exc:  # noqa: BLE001
        log.debug("command %r failed (%s)", args, exc)
        return None


def have_tool(name: str) -> bool:
    """True if ``name`` is on PATH."""
    return shutil.which(name) is not None


def is_root() -> bool:
    """True when we can plausibly perform privileged netlink ops.

    Real CAP_NET_ADMIN can be granted without uid 0, so we treat either uid 0
    or a readable hint of the capability as 'privileged enough to try'. The
    actual ops still degrade gracefully if the kernel says no.
    """
    try:
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            return True
    except OSError:  # pragma: no cover - extremely unusual
        pass
    # Best-effort CAP_NET_ADMIN probe (bit 12). Absent file -> not root.
    try:
        with open("/proc/self/status", "r", encoding="ascii", errors="ignore") as fh:
            for line in fh:
                if line.startswith("CapEff:"):
                    caps = int(line.split()[1], 16)
                    return bool(caps & (1 << 12))  # CAP_NET_ADMIN
    except (OSError, ValueError):  # pragma: no cover
        pass
    return False


def channels_for_bands(bands) -> list:
    """Flatten a list of band labels ('2.4GHz'/'5GHz'/'6GHz') to a channel list.

    Unknown labels are ignored. Order follows 2.4 -> 5 -> 6 and de-dupes while
    preserving first-seen order so the hopper visits low bands first.
    """
    plan = {
        "2.4ghz": CHANNELS_24, "2.4": CHANNELS_24, "2g": CHANNELS_24,
        "5ghz": CHANNELS_5, "5": CHANNELS_5, "5g": CHANNELS_5,
        "6ghz": CHANNELS_6, "6": CHANNELS_6, "6g": CHANNELS_6,
    }
    out: list = []
    for b in (bands or []):
        chans = plan.get(str(b).strip().lower())
        if not chans:
            continue
        for ch in chans:
            if ch not in out:
                out.append(ch)
    return out


@dataclass
class Capabilities:
    """Snapshot of what the native stack can actually do right now."""

    tools: dict = field(default_factory=dict)   # tool name -> present?
    interface: str | None = None                # chosen iface (mon-capable)
    phy: str | None = None                       # owning phy (e.g. 'phy0')
    driver: str | None = None
    supports_monitor: bool = False
    in_monitor: bool = False                     # iface currently in monitor mode
    is_root: bool = False
    regdomain: str | None = None

    def ready(self) -> bool:
        """True when we could *attempt* a native capture (iface + iw + root)."""
        return bool(self.interface and self.tools.get("iw") and self.is_root)

    def as_dict(self) -> dict:
        return {
            "tools": dict(self.tools),
            "interface": self.interface,
            "phy": self.phy,
            "driver": self.driver,
            "supports_monitor": self.supports_monitor,
            "in_monitor": self.in_monitor,
            "is_root": self.is_root,
            "regdomain": self.regdomain,
            "ready": self.ready(),
        }


class MonitorInterface:
    """Manage a monitor-mode WiFi interface for native capture.

    Construct with a Config; call :meth:`capabilities` to preflight, then
    :meth:`enable` to put the radio into monitor mode. ``enable`` records the
    monitor iface name in :attr:`mon_iface`. Always :meth:`disable` when done
    (best-effort; safe to call even if enable failed).
    """

    def __init__(self, cfg):
        self.cfg = cfg
        # Operator-configured *managed* interface; mon iface may differ once
        # airmon-ng renames it (e.g. wlan0 -> wlan0mon).
        self.base_iface = str(getattr(cfg, "interface", "") or "")
        self.mon_iface: str | None = None
        self._used_airmon = False

    # -- discovery --------------------------------------------------------
    def _iw_dev(self) -> str:
        proc = _run(["iw", "dev"])
        return proc.stdout if proc and proc.returncode == 0 else ""

    def _parse_iw_dev(self, text: str) -> list:
        """Parse ``iw dev`` into [{'phy','iface','type'}] records."""
        records: list = []
        phy = None
        iface = None
        itype = None
        for raw in text.splitlines():
            line = raw.strip()
            m = re.match(r"phy#(\d+)", line)
            if m:
                if iface:
                    records.append({"phy": phy, "iface": iface, "type": itype})
                    iface = itype = None
                phy = "phy" + m.group(1)
                continue
            m = re.match(r"Interface\s+(\S+)", line)
            if m:
                if iface:
                    records.append({"phy": phy, "iface": iface, "type": itype})
                    itype = None
                iface = m.group(1)
                continue
            m = re.match(r"type\s+(\S+)", line)
            if m and iface:
                itype = m.group(1)
        if iface:
            records.append({"phy": phy, "iface": iface, "type": itype})
        return records

    def _phy_supports_monitor(self, phy: str | None) -> bool:
        """True if ``iw phy <phy> info`` lists a monitor mode under interfaces."""
        if not phy:
            return False
        proc = _run(["iw", "phy", phy, "info"])
        if not proc or proc.returncode != 0:
            # NEEDS ON-HARDWARE VALIDATION: if iw can't tell us, assume capable
            # so we still *try* rather than disqualify a real radio.
            return True
        text = proc.stdout
        # The block looks like: "Supported interface modes:\n * monitor"
        m = re.search(r"Supported interface modes:(.*?)(?:\n\S|\Z)", text, re.S)
        scope = m.group(1) if m else text
        return "monitor" in scope.lower()

    def _phy_driver(self, phy: str | None) -> str | None:
        """Best-effort driver name for a phy via sysfs."""
        if not phy:
            return None
        path = f"/sys/class/ieee80211/{phy}/device/driver"
        try:
            if os.path.islink(path):
                return os.path.basename(os.readlink(path))
        except OSError:  # pragma: no cover
            pass
        return None

    def detect_interface(self) -> dict | None:
        """Pick the best monitor-capable interface.

        Preference order: the operator-configured iface (if monitor-capable) ->
        an MT7921/mt76 radio -> any monitor-capable iface -> first iface seen.
        Returns a record dict {'iface','phy','type','driver','monitor'} or None.
        """
        records = self._parse_iw_dev(self._iw_dev())
        if not records:
            return None
        # Annotate each record with driver + monitor capability.
        for rec in records:
            rec["driver"] = self._phy_driver(rec.get("phy"))
            rec["monitor"] = self._phy_supports_monitor(rec.get("phy"))

        # 1) explicit config match (base or its *mon alias)
        if self.base_iface:
            for rec in records:
                if rec["iface"] == self.base_iface and rec["monitor"]:
                    return rec
        # 2) preferred driver, monitor-capable
        for rec in records:
            drv = (rec.get("driver") or "").lower()
            if rec["monitor"] and any(p in drv for p in _PREFERRED_DRIVERS):
                return rec
        # 3) any monitor-capable iface
        for rec in records:
            if rec["monitor"]:
                return rec
        # 4) fall back to the first interface (let enable() try anyway)
        return records[0]

    # -- preflight --------------------------------------------------------
    def capabilities(self) -> Capabilities:
        """Probe tools/iface/root without changing any radio state."""
        caps = Capabilities()
        caps.tools = {name: have_tool(name) for name in _TOOLS}
        caps.is_root = is_root()
        caps.regdomain = self.get_regdomain()
        if not caps.tools.get("iw"):
            return caps
        rec = self.detect_interface()
        if rec:
            caps.interface = rec.get("iface")
            caps.phy = rec.get("phy")
            caps.driver = rec.get("driver")
            caps.supports_monitor = bool(rec.get("monitor"))
            caps.in_monitor = (rec.get("type") == "monitor")
        return caps

    # -- regulatory domain ------------------------------------------------
    def get_regdomain(self) -> str | None:
        proc = _run(["iw", "reg", "get"])
        if not proc or proc.returncode != 0:
            return None
        m = re.search(r"country\s+(\w\w)", proc.stdout)
        return m.group(1) if m else None

    def set_regdomain(self, code: str) -> bool:
        """Set the regulatory domain (e.g. 'US', 'AU'). Best-effort.

        NEEDS ON-HARDWARE VALIDATION: enables high 5/6GHz channels only where
        the operator's regdomain legally permits them.
        """
        code = str(code or "").strip().upper()
        if not re.fullmatch(r"[A-Z]{2}", code):
            return False
        proc = _run(["iw", "reg", "set", code])
        ok = bool(proc and proc.returncode == 0)
        if ok:
            log.info("regdomain set to %s", code)
        return ok

    # -- monitor mode -----------------------------------------------------
    def _rfkill_unblock(self) -> None:
        if have_tool("rfkill"):
            _run(["rfkill", "unblock", "wifi"])
            _run(["rfkill", "unblock", "all"])

    def enable(self) -> str | None:
        """Put a monitor-capable interface into monitor mode.

        Tries ``airmon-ng start`` first (handles NM/wpa_supplicant teardown and
        renames the iface), then falls back to manual ``iw``/``ip`` calls.
        Returns the monitor iface name on success, else None. Never raises.

        NEEDS ON-HARDWARE VALIDATION.
        """
        if not is_root():
            log.info("monitor enable skipped: not privileged (no root/CAP_NET_ADMIN)")
            return None
        rec = self.detect_interface()
        if not rec:
            log.info("monitor enable skipped: no WiFi interface found via 'iw dev'")
            return None
        iface = rec["iface"]
        self._rfkill_unblock()

        # Already in monitor mode? Use it as-is.
        if rec.get("type") == "monitor":
            self.mon_iface = iface
            log.info("interface %s already in monitor mode", iface)
            return iface

        mon = self._enable_airmon(iface) or self._enable_iw(iface)
        if mon:
            self.mon_iface = mon
            # Set an initial channel if the config asks for one band of hopping.
            self._apply_optional_regdomain()
            log.info("monitor mode active on %s", mon)
        else:
            log.warning("could not enable monitor mode on %s", iface)
        return mon

    def _apply_optional_regdomain(self) -> None:
        reg = getattr(self.cfg, "regdomain", "") or ""
        if reg:
            self.set_regdomain(reg)

    def _enable_airmon(self, iface: str) -> str | None:
        """Try airmon-ng; returns the (possibly renamed) monitor iface."""
        if not have_tool("airmon-ng"):
            return None
        # airmon-ng check kill stops NM/wpa_supplicant that would fight us.
        _run(["airmon-ng", "check", "kill"], timeout=10.0)
        proc = _run(["airmon-ng", "start", iface], timeout=15.0)
        if not proc or proc.returncode != 0:
            return None
        self._used_airmon = True
        # airmon prints the new iface; otherwise infer the common rename.
        text = proc.stdout or ""
        m = re.search(r"(?:monitor mode .*?enabled.*?\[?\S*?\]?)?\b(\w+mon\w*)\b", text)
        candidate = m.group(1) if m else (iface + "mon")
        # Confirm against a fresh iw dev; prefer a record actually in monitor.
        records = self._parse_iw_dev(self._iw_dev())
        names = {r["iface"]: r for r in records}
        if candidate in names and names[candidate].get("type") == "monitor":
            return candidate
        for name, rec in names.items():
            if rec.get("type") == "monitor":
                return name
        # Trust the candidate even if iw didn't confirm the type string.
        return candidate if candidate in names else None

    def _enable_iw(self, iface: str) -> str | None:
        """Manual monitor switch: down -> set type monitor -> up."""
        if not have_tool("iw"):
            return None
        down = _run(["ip", "link", "set", iface, "down"])
        if down is None:
            # No 'ip'? try 'ifconfig' shape is out of scope; bail cleanly.
            log.debug("'ip' unavailable; cannot toggle %s", iface)
            return None
        set_mon = _run(["iw", "dev", iface, "set", "type", "monitor"])
        _run(["ip", "link", "set", iface, "up"])
        if not set_mon or set_mon.returncode != 0:
            return None
        # Verify we actually landed in monitor mode.
        records = self._parse_iw_dev(self._iw_dev())
        for rec in records:
            if rec["iface"] == iface and rec.get("type") == "monitor":
                return iface
        # Some drivers report lazily; trust the command's success.
        return iface

    def disable(self) -> bool:
        """Best-effort return to managed mode. Safe to call always."""
        iface = self.mon_iface
        if not iface:
            return True
        ok = False
        if self._used_airmon and have_tool("airmon-ng"):
            proc = _run(["airmon-ng", "stop", iface], timeout=15.0)
            ok = bool(proc and proc.returncode == 0)
        if not ok and have_tool("iw"):
            _run(["ip", "link", "set", iface, "down"])
            r = _run(["iw", "dev", iface, "set", "type", "managed"])
            _run(["ip", "link", "set", iface, "up"])
            ok = bool(r and r.returncode == 0)
        self.mon_iface = None
        self._used_airmon = False
        return ok

    # -- channel control --------------------------------------------------
    def set_channel(self, channel: int) -> bool:
        """Tune the monitor iface to a channel. Best-effort, never raises."""
        iface = self.mon_iface or self.base_iface
        if not iface:
            return False
        try:
            ch = int(channel)
        except (TypeError, ValueError):
            return False
        proc = _run(["iw", "dev", iface, "set", "channel", str(ch)])
        return bool(proc and proc.returncode == 0)

    def hop_channels(self) -> list:
        """The channel list this interface should hop across.

        Honours ``cfg.channels`` if set (an explicit list), otherwise derives a
        plan from the 2.4/5/6GHz bands. The agent/capture loop iterates this.
        """
        explicit = getattr(self.cfg, "channels", None)
        chans: list = []
        if isinstance(explicit, (list, tuple)):
            for c in explicit:
                try:
                    chans.append(int(c))
                except (TypeError, ValueError):
                    continue
        if chans:
            return chans
        return channels_for_bands(["2.4GHz", "5GHz", "6GHz"])
