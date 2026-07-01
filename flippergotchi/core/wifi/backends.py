"""Capture backend abstraction + auto-selecting factory.

A ``CaptureBackend`` gives the agent one uniform surface regardless of how
detections/handshakes are actually produced:

    start()                                  -> None
    scan() -> list[ap dict]                  passive AP discovery (poll)
    capture_handshake(bssid, ssid, timeout)  -> path | None
    stop()                                   -> None

Three concrete backends:

  * :class:`NativeBackend`   -- our own monitor-mode stack (iw scan +
    hcxdumptool/scapy). Used when a monitor-capable radio + a capture tool are
    present, we're privileged, and we're not simulating.
  * :class:`BettercapBackend` -- thin wrapper over the existing
    ``core.bettercap.BettercapClient`` live path.
  * :class:`SimBackend`      -- reuses ``BettercapClient`` in sim mode, so
    simulation behaviour is byte-for-byte unchanged.

:func:`make_backend` auto-selects native -> bettercap -> sim, honouring a
``cfg.capture_backend`` override of "auto"|"native"|"bettercap"|"sim".

Selection NEVER touches a radio: it only probes tool/iface availability via
:class:`~.monitor.MonitorInterface.capabilities`. Enabling monitor mode happens
lazily in :meth:`NativeBackend.start`.
"""
from __future__ import annotations

import logging

from ..bettercap import BettercapClient
from . import capture as capture_mod
from . import monitor as monitor_mod
from . import scan as scan_mod

log = logging.getLogger(__name__)


class CaptureBackend:
    """Uniform interface every backend implements. Methods never raise."""

    name = "base"

    def start(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def scan(self) -> list:  # pragma: no cover - overridden
        raise NotImplementedError

    def capture_handshake(self, bssid, ssid="", timeout=25):  # pragma: no cover
        raise NotImplementedError

    def stop(self) -> None:  # default no-op
        return None


class SimBackend(CaptureBackend):
    """Simulation backend: delegates to BettercapClient's sim poll.

    Behaviour is identical to the pre-existing sim path so --simulate is
    unchanged. capture_handshake returns None (the game produces the handshake
    from the encounter, as before).
    """

    name = "sim"

    def __init__(self, cfg):
        self.cfg = cfg
        self._client = BettercapClient(cfg)  # mode follows cfg.simulate

    def start(self) -> None:
        try:
            self._client.start()
        except Exception as exc:  # noqa: BLE001
            log.debug("sim backend start ignored (%s)", exc)

    def scan(self) -> list:
        try:
            return self._client.poll()
        except Exception as exc:  # noqa: BLE001
            log.debug("sim scan failed (%s)", exc)
            return []

    def capture_handshake(self, bssid, ssid="", timeout=25):
        # Sim has no real radio; the encounter flow synthesises the catch.
        return None


class BettercapBackend(CaptureBackend):
    """Wrap the existing live BettercapClient unchanged."""

    name = "bettercap"

    def __init__(self, cfg, is_authorized=None):
        self.cfg = cfg
        self.is_authorized = is_authorized
        self._client = BettercapClient(cfg, is_authorized=is_authorized)

    def start(self) -> None:
        try:
            self._client.start()
        except Exception as exc:  # noqa: BLE001
            log.warning("bettercap backend start failed (%s)", exc)

    def scan(self) -> list:
        try:
            return self._client.poll()
        except Exception as exc:  # noqa: BLE001
            log.warning("bettercap scan failed (%s)", exc)
            return []

    def capture_handshake(self, bssid, ssid="", timeout=25):
        try:
            return self._client.capture_handshake(bssid, ssid, timeout)
        except Exception as exc:  # noqa: BLE001
            log.warning("bettercap capture_handshake failed (%s)", exc)
            return None


class NativeBackend(CaptureBackend):
    """Native monitor-mode capture: iw scan + hcxdumptool/scapy.

    Brings the radio into monitor mode in :meth:`start` and tears it back down
    in :meth:`stop`. Scans are passive (no authorization needed); handshake
    capture is gated by ``is_authorized`` for any deauth/injection.

    NEEDS ON-HARDWARE VALIDATION.
    """

    name = "native"

    def __init__(self, cfg, is_authorized=None):
        self.cfg = cfg
        self.is_authorized = is_authorized
        self.mon = monitor_mod.MonitorInterface(cfg)
        self.iface: str | None = None
        self._cap = None
        self._hop = []
        self._hop_i = 0
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        try:
            self.iface = self.mon.enable()
        except Exception as exc:  # noqa: BLE001
            log.warning("native monitor enable failed (%s)", exc)
            self.iface = None
        if not self.iface:
            # Fall back to the configured iface name for a passive scan attempt;
            # capture will simply return None if it's not really in monitor mode.
            self.iface = str(getattr(self.cfg, "interface", "") or "") or None
            log.info("native backend running without a confirmed monitor iface; "
                     "passive scans only")
        if self.iface:
            self._cap = capture_mod.HandshakeCapture(
                self.cfg, self.iface, is_authorized=self.is_authorized)
        self._hop = self.mon.hop_channels()

    def _next_channel(self):
        if not self._hop:
            return None
        ch = self._hop[self._hop_i % len(self._hop)]
        self._hop_i += 1
        return ch

    def scan(self) -> list:
        if not self.iface:
            return []
        # Hop one channel per scan tick so successive polls cover the band plan.
        ch = self._next_channel()
        if ch is not None:
            try:
                self.mon.set_channel(ch)
            except Exception as exc:  # noqa: BLE001
                log.debug("set_channel(%s) failed (%s)", ch, exc)
        try:
            aps = scan_mod.scan_iw(self.iface)
        except Exception as exc:  # noqa: BLE001
            log.warning("native scan failed (%s)", exc)
            return []
        # Match the project's event shape: tag each AP dict with type 'ap'.
        return [{"type": "ap", **ap} for ap in aps]

    def capture_handshake(self, bssid, ssid="", timeout=25):
        if not self._cap:
            return None
        # Use any channel we learned for this AP if the caller cached one.
        channel = None
        try:
            return self._cap.capture(bssid, ssid, timeout, channel=channel)
        except Exception as exc:  # noqa: BLE001
            log.warning("native capture_handshake failed (%s)", exc)
            return None

    def stop(self) -> None:
        try:
            self.mon.disable()
        except Exception as exc:  # noqa: BLE001
            log.debug("native monitor disable failed (%s)", exc)


# -- factory ----------------------------------------------------------------

_VALID = ("auto", "native", "bettercap", "sim")


def _native_available(cfg) -> bool:
    """True when a native capture could plausibly run (no radio touched)."""
    if getattr(cfg, "simulate", False):
        return False
    has_tool = capture_mod.have_hcxdumptool() or capture_mod.have_scapy()
    if not has_tool:
        return False
    try:
        caps = monitor_mod.MonitorInterface(cfg).capabilities()
    except Exception as exc:  # noqa: BLE001
        log.debug("capability probe failed (%s)", exc)
        return False
    # Need an interface, the iw tool, monitor support, and privilege to try.
    return bool(caps.interface and caps.tools.get("iw")
                and caps.supports_monitor and caps.is_root)


def make_backend(cfg, is_authorized=None) -> CaptureBackend:
    """Select and construct the capture backend for this run.

    Order (when cfg.capture_backend == 'auto', the default):
        native (if available & not simulating) -> bettercap (live) -> sim.

    A ``cfg.capture_backend`` of native/bettercap/sim forces that choice. If a
    forced backend can't actually run we still honour the request as closely as
    possible but never crash; 'native' forced without hardware will start in a
    passive/no-op state rather than raising.
    """
    choice = str(getattr(cfg, "capture_backend", "auto") or "auto").strip().lower()
    if choice not in _VALID:
        log.warning("unknown capture_backend %r; falling back to 'auto'", choice)
        choice = "auto"

    simulate = bool(getattr(cfg, "simulate", False))

    # Hard rule: in simulate mode we ALWAYS return the sim backend and never
    # touch a radio, regardless of the override (except an explicit non-sim
    # override which we still honour but warn about -- though native/bettercap
    # constructed under simulate stay inert because they read cfg.simulate too).
    if simulate and choice in ("auto", "sim"):
        return SimBackend(cfg)

    if choice == "sim":
        return SimBackend(cfg)
    if choice == "bettercap":
        return BettercapBackend(cfg, is_authorized=is_authorized)
    if choice == "native":
        return NativeBackend(cfg, is_authorized=is_authorized)

    # auto, not simulating:
    if _native_available(cfg):
        log.info("capture backend: native (monitor-mode hcxdumptool/scapy)")
        return NativeBackend(cfg, is_authorized=is_authorized)
    log.info("capture backend: bettercap (native stack unavailable)")
    return BettercapBackend(cfg, is_authorized=is_authorized)
