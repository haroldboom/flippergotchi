"""Native WiFi capture stack for Flippergotchi.

A self-contained, defensive layer over the Flipper One's monitor-mode radio
that degrades cleanly to simulation when there's no hardware/root. Importing
this package pulls in NO radio tools and NO optional deps (scapy is import-
guarded inside :mod:`capture`).

Public surface:

    make_backend(cfg, is_authorized=None) -> CaptureBackend
        Auto-select native -> bettercap -> sim (override via cfg.capture_backend).

    CaptureBackend / NativeBackend / BettercapBackend / SimBackend
        The backend classes.

    MonitorInterface, Capabilities
        Monitor-mode iface management + preflight.

    HandshakeCapture
        Targeted handshake/PMKID capture (authorization-gated injection).

    Passive scan helpers: scan_iw, parse_iw_scan, parse_airodump_csv.
"""
from __future__ import annotations

from .backends import (
    BettercapBackend,
    CaptureBackend,
    NativeBackend,
    SimBackend,
    make_backend,
)
from .capture import HandshakeCapture, have_hcxdumptool, have_scapy
from .monitor import (
    Capabilities,
    MonitorInterface,
    channels_for_bands,
)
from .scan import (
    parse_airodump_csv,
    parse_iw_scan,
    read_airodump_csv,
    scan_iw,
)

__all__ = [
    "make_backend",
    "CaptureBackend",
    "NativeBackend",
    "BettercapBackend",
    "SimBackend",
    "MonitorInterface",
    "Capabilities",
    "channels_for_bands",
    "HandshakeCapture",
    "have_hcxdumptool",
    "have_scapy",
    "scan_iw",
    "parse_iw_scan",
    "parse_airodump_csv",
    "read_airodump_csv",
]
