"""Native WiFi capture stack: parsers, helpers, capabilities, factory, gating.

All radio-free: subprocess/scapy/tool presence is monkeypatched. No real
interface is ever touched.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flippergotchi.config import Config
from flippergotchi.core.wifi import (
    MonitorInterface,
    backends,
    capture as capture_mod,
    monitor as monitor_mod,
    scan as scan_mod,
)
from flippergotchi.core.wifi.backends import (
    BettercapBackend,
    NativeBackend,
    SimBackend,
    make_backend,
)


# -- iw scan parser ---------------------------------------------------------

IW_SCAN = """\
BSS aa:bb:cc:dd:ee:01(on wlan0)
\tfreq: 2437
\tsignal: -42.00 dBm
\tSSID: HomeNet
\tRSN:\t * Version: 1
\t\t * Authentication suites: PSK
\tWPS:\t * Version: 1.0
BSS aa:bb:cc:dd:ee:02(on wlan0)
\tfreq: 5180
\tsignal: -67.00 dBm
\tSSID: OfficeGuest
\tWPA:\t * Version: 1
\t\t * Authentication suites: PSK
BSS aa:bb:cc:dd:ee:03(on wlan0)
\tfreq: 5955
\tsignal: -55.00 dBm
\tSSID: Modern6E
\tRSN:\t * Authentication suites: SAE
BSS aa:bb:cc:dd:ee:04(on wlan0)
\tfreq: 2412
\tsignal: -70.00 dBm
\tSSID: CorpNet
\tRSN:\t * Authentication suites: IEEE 802.1X
BSS aa:bb:cc:dd:ee:05(on wlan0)
\tfreq: 2462
\tsignal: -80.00 dBm
\tSSID: OldRouter
\tcapability: ESS Privacy
BSS aa:bb:cc:dd:ee:06(on wlan0)
\tfreq: 2412
\tsignal: -50.00 dBm
\tSSID: FreeWifi
\tcapability: ESS
"""


def test_parse_iw_scan_basic_shape_and_filtering():
    aps = scan_mod.parse_iw_scan(IW_SCAN)
    by_bssid = {a["bssid"]: a for a in aps}

    # WPA3 (SAE) and Enterprise (802.1X) are dropped.
    assert "AA:BB:CC:DD:EE:03" not in by_bssid  # SAE
    assert "AA:BB:CC:DD:EE:04" not in by_bssid  # 802.1X

    # WPA2 (RSN+PSK), 2.4GHz, WPS present.
    home = by_bssid["AA:BB:CC:DD:EE:01"]
    assert home["ssid"] == "HomeNet"
    assert home["encryption"] == "wpa2"
    assert home["band"] == "2.4GHz"
    assert home["wps"] is True
    assert home["signal"] == -42
    assert set(home.keys()) == {
        "bssid", "ssid", "encryption", "band", "wps", "clients", "signal"}

    # WPA (TKIP-era), 5GHz.
    office = by_bssid["AA:BB:CC:DD:EE:02"]
    assert office["encryption"] == "wpa"
    assert office["band"] == "5GHz"

    # Privacy bit, no RSN/WPA -> WEP.
    old = by_bssid["AA:BB:CC:DD:EE:05"]
    assert old["encryption"] == "wep"

    # No privacy -> open.
    free = by_bssid["AA:BB:CC:DD:EE:06"]
    assert free["encryption"] == "open"


def test_parse_iw_scan_handles_garbage():
    assert scan_mod.parse_iw_scan("") == []
    assert scan_mod.parse_iw_scan("not a scan at all\nrandom") == []


# -- airodump CSV parser ----------------------------------------------------

AIRODUMP_CSV = """\
BSSID, First time seen, Last time seen, channel, Speed, Privacy, Cipher, Authentication, Power, # beacons, # IV, LAN IP, ID-length, ESSID, Key

AA:BB:CC:DD:EE:01, 2026-06-17 10:00:00, 2026-06-17 10:05:00, 6, 130, WPA2, CCMP, PSK, -45, 100, 0, 0.0.0.0, 7, HomeNet,
AA:BB:CC:DD:EE:07, 2026-06-17 10:00:00, 2026-06-17 10:05:00, 36, 130, WPA2, CCMP, MGT, -60, 50, 0, 0.0.0.0, 9, EnterpriseAP,
AA:BB:CC:DD:EE:08, 2026-06-17 10:00:00, 2026-06-17 10:05:00, 1, 54, OPN, , , -70, 20, 0, 0.0.0.0, 8, CafeWifi,

Station MAC, First time seen, Last time seen, Power, # packets, BSSID, Probed ESSIDs
11:22:33:44:55:66, 2026-06-17 10:01:00, 2026-06-17 10:05:00, -50, 30, AA:BB:CC:DD:EE:01,
11:22:33:44:55:77, 2026-06-17 10:01:00, 2026-06-17 10:05:00, -52, 22, AA:BB:CC:DD:EE:01,
"""


def test_parse_airodump_csv():
    aps = scan_mod.parse_airodump_csv(AIRODUMP_CSV)
    by_bssid = {a["bssid"]: a for a in aps}

    # Enterprise (MGT) dropped.
    assert "AA:BB:CC:DD:EE:07" not in by_bssid

    home = by_bssid["AA:BB:CC:DD:EE:01"]
    assert home["encryption"] == "wpa2"
    assert home["band"] == "2.4GHz"
    assert home["ssid"] == "HomeNet"
    assert home["clients"] == 2          # two stations associated
    assert home["signal"] == -45

    cafe = by_bssid["AA:BB:CC:DD:EE:08"]
    assert cafe["encryption"] == "open"
    assert cafe["clients"] == 0


# -- channel/band helpers ---------------------------------------------------

def test_channels_for_bands():
    assert monitor_mod.channels_for_bands(["2.4GHz"]) == monitor_mod.CHANNELS_24
    fives = monitor_mod.channels_for_bands(["5GHz"])
    assert 36 in fives and 165 in fives
    sixes = monitor_mod.channels_for_bands(["6GHz"])
    assert 5 in sixes and 229 in sixes
    # unknown labels ignored, order preserved + de-duped
    mixed = monitor_mod.channels_for_bands(["2.4", "bogus", "2.4ghz"])
    assert mixed == monitor_mod.CHANNELS_24


def test_hop_channels_honours_explicit_config():
    cfg = Config()
    cfg.channels = [1, 6, 11, 36]
    mon = MonitorInterface(cfg)
    assert mon.hop_channels() == [1, 6, 11, 36]


def test_hop_channels_default_plan():
    cfg = Config()
    mon = MonitorInterface(cfg)
    chans = mon.hop_channels()
    assert 1 in chans and 36 in chans  # spans bands


# -- capabilities with tools absent -----------------------------------------

def test_capabilities_no_tools(monkeypatch):
    # No tools on PATH, not root.
    monkeypatch.setattr(monitor_mod.shutil, "which", lambda name: None)
    monkeypatch.setattr(monitor_mod, "is_root", lambda: False)
    cfg = Config()
    caps = MonitorInterface(cfg).capabilities()
    assert caps.tools == {"iw": False, "ip": False,
                          "rfkill": False, "airmon-ng": False}
    assert caps.interface is None
    assert caps.is_root is False
    assert caps.ready() is False
    d = caps.as_dict()
    assert d["ready"] is False and d["interface"] is None


def test_detect_interface_prefers_mt7921(monkeypatch):
    cfg = Config()
    cfg.interface = ""
    mon = MonitorInterface(cfg)
    iw_dev = (
        "phy#0\n"
        "\tInterface wlan0\n\t\ttype managed\n"
        "phy#1\n"
        "\tInterface wlan1\n\t\ttype managed\n"
    )
    monkeypatch.setattr(mon, "_iw_dev", lambda: iw_dev)
    monkeypatch.setattr(mon, "_phy_supports_monitor", lambda phy: True)

    def fake_driver(phy):
        return "mt7921e" if phy == "phy1" else "iwlwifi"
    monkeypatch.setattr(mon, "_phy_driver", fake_driver)

    rec = mon.detect_interface()
    assert rec["iface"] == "wlan1"     # the MT7921 radio wins
    assert rec["driver"] == "mt7921e"


# -- factory selection ------------------------------------------------------

def test_factory_returns_sim_under_simulate():
    cfg = Config()
    cfg.simulate = True
    backend = make_backend(cfg)
    assert isinstance(backend, SimBackend)
    assert backend.name == "sim"
    # Sim never touches a radio and yields no real handshake.
    backend.start()
    assert backend.capture_handshake("AA:BB:CC:DD:EE:01", "HomeNet", 1) is None
    assert isinstance(backend.scan(), list)


def test_factory_override_sim_even_when_live():
    cfg = Config()
    cfg.simulate = False
    cfg.capture_backend = "sim"
    assert isinstance(make_backend(cfg), SimBackend)


def test_factory_auto_falls_back_to_bettercap(monkeypatch):
    cfg = Config()
    cfg.simulate = False
    # Native unavailable: no capture tools.
    monkeypatch.setattr(capture_mod, "have_hcxdumptool", lambda: False)
    monkeypatch.setattr(capture_mod, "have_scapy", lambda: False)
    backend = make_backend(cfg)
    assert isinstance(backend, BettercapBackend)


def test_factory_auto_selects_native_when_available(monkeypatch):
    cfg = Config()
    cfg.simulate = False
    monkeypatch.setattr(capture_mod, "have_hcxdumptool", lambda: True)

    class FakeCaps:
        interface = "wlan0"
        tools = {"iw": True}
        supports_monitor = True
        is_root = True
    monkeypatch.setattr(
        monitor_mod.MonitorInterface, "capabilities", lambda self: FakeCaps())
    backend = make_backend(cfg)
    assert isinstance(backend, NativeBackend)


def test_factory_unknown_override_falls_back(monkeypatch):
    cfg = Config()
    cfg.simulate = False
    cfg.capture_backend = "bogus"
    monkeypatch.setattr(capture_mod, "have_hcxdumptool", lambda: False)
    monkeypatch.setattr(capture_mod, "have_scapy", lambda: False)
    # bogus -> auto -> bettercap (native unavailable)
    assert isinstance(make_backend(cfg), BettercapBackend)


# -- authorization gating on capture ----------------------------------------

def test_capture_refuses_deauth_when_unauthorized(monkeypatch):
    """A denied gate => no hcxdumptool active attack flags, no deauth."""
    cfg = Config()
    cfg.capture_dir = "/tmp/fg-test-captures"

    sent = {"deauth": 0, "hcx_args": None}

    # No scapy path; force hcxdumptool path and capture its argv.
    monkeypatch.setattr(capture_mod, "have_hcxdumptool", lambda: True)
    monkeypatch.setattr(capture_mod, "have_scapy", lambda: False)
    monkeypatch.setattr(capture_mod.shutil, "which",
                        lambda name: "/usr/bin/hcxdumptool")

    def fake_run(args, **kwargs):
        sent["hcx_args"] = args

        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()
    monkeypatch.setattr(capture_mod.subprocess, "run", fake_run)

    # is_authorized returns False -> passive only.
    cap = capture_mod.HandshakeCapture(
        cfg, "wlan0mon", is_authorized=lambda b, s: False)
    # No real file is written, so capture() returns None; we assert on argv.
    cap.capture("AA:BB:CC:DD:EE:99", "StrangerNet", timeout=1)

    args = sent["hcx_args"]
    assert args is not None
    # Passive flags MUST be present when unauthorized.
    assert "--disable_deauthentication" in args
    assert "--disable_disassociation" in args
    assert "--disable_ap_attacks" in args


def test_capture_allows_attack_flags_when_authorized(monkeypatch):
    cfg = Config()
    cfg.capture_dir = "/tmp/fg-test-captures"
    sent = {"hcx_args": None}

    monkeypatch.setattr(capture_mod, "have_hcxdumptool", lambda: True)
    monkeypatch.setattr(capture_mod, "have_scapy", lambda: False)
    monkeypatch.setattr(capture_mod.shutil, "which",
                        lambda name: "/usr/bin/hcxdumptool")

    def fake_run(args, **kwargs):
        sent["hcx_args"] = args

        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()
    monkeypatch.setattr(capture_mod.subprocess, "run", fake_run)

    cap = capture_mod.HandshakeCapture(
        cfg, "wlan0mon", is_authorized=lambda b, s: True)
    cap.capture("AA:BB:CC:DD:EE:01", "HomeNet", timeout=1)

    args = sent["hcx_args"]
    assert args is not None
    # Authorized: NO passive-disable flags (active attacks permitted).
    assert "--disable_deauthentication" not in args
    assert "--disable_ap_attacks" not in args


def test_capture_gate_missing_is_passive(monkeypatch):
    """No is_authorized callable at all => treated as unauthorized/passive."""
    cfg = Config()
    cap = capture_mod.HandshakeCapture(cfg, "wlan0mon", is_authorized=None)
    assert cap._authorized("AA:BB:CC:DD:EE:01", "HomeNet") is False


def test_capture_gate_exception_fails_closed():
    cfg = Config()

    def boom(b, s):
        raise RuntimeError("broken gate")
    cap = capture_mod.HandshakeCapture(cfg, "wlan0mon", is_authorized=boom)
    assert cap._authorized("x", "y") is False


def test_capture_never_raises_without_tools(monkeypatch):
    cfg = Config()
    monkeypatch.setattr(capture_mod, "have_hcxdumptool", lambda: False)
    monkeypatch.setattr(capture_mod, "have_scapy", lambda: False)
    cap = capture_mod.HandshakeCapture(cfg, "wlan0mon",
                                       is_authorized=lambda b, s: True)
    assert cap.capture("AA:BB:CC:DD:EE:01", "HomeNet", timeout=1) is None


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
