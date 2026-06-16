"""Authorization scope guard + doctor preflight readout.

No hardware/root/files required: probes are monkeypatched and audit/allowlist
files go to tmp_path. Asserts deny-by-default, robustness on weird input, the
JSONL audit trail, and the doctor report's section/marker shape.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flippergotchi.config import Config
from flippergotchi.core import authz, preflight as preflight_mod
from flippergotchi.game import doctor


# -- in_scope: home_networks ------------------------------------------------

def test_in_scope_matches_home_networks_ssid_and_bssid():
    cfg = Config()
    cfg.home_networks = ["MyHome", "AA:BB:CC"]
    # SSID substring, case-insensitive.
    assert authz.in_scope("11:22:33:44:55:66", "myhome-5g", cfg) is True
    # BSSID substring.
    assert authz.in_scope("AA:BB:CC:DD:EE:FF", "Unknown", cfg) is True
    # Neither -> denied.
    assert authz.in_scope("99:88:77:66:55:44", "StrangerNet", cfg) is False


def test_in_scope_empty_scope_denies_by_default():
    cfg = Config()           # home_networks defaults to []
    cfg.home_networks = []
    cfg.allowlist_path = "/nonexistent/allowlist.txt"
    assert authz.in_scope("AA:BB:CC:DD:EE:FF", "HomeNet", cfg) is False


def test_in_scope_bare_string_home_networks_not_iterated_char_by_char():
    cfg = Config()
    cfg.home_networks = "HomeNet"      # a bare string, not a list
    # Must match as a whole needle, not as individual characters.
    assert authz.in_scope("AA:BB:CC:DD:EE:FF", "HomeNet-Guest", cfg) is True
    # A single char from the string must NOT spuriously match.
    assert authz.in_scope("00:00:00:00:00:00", "zzz", cfg) is False


def test_in_scope_never_crashes_on_weird_input():
    cfg = Config()
    cfg.home_networks = "Home"
    # None / ints / empty must all be handled without raising.
    assert authz.in_scope(None, None, cfg) is False
    assert authz.in_scope(123, 456, cfg) is False
    assert authz.in_scope("", "", cfg) is False

    # home_networks itself being None / an int.
    cfg.home_networks = None
    assert authz.in_scope("AA:BB", "Home", cfg) is False
    cfg.home_networks = 42
    assert authz.in_scope("AA:BB", "Home", cfg) is False


# -- allowlist file ---------------------------------------------------------

def test_load_allowlist_parses_comments_and_blanks(tmp_path):
    p = tmp_path / "allowlist.txt"
    p.write_text(
        "# my gear\n"
        "AA:BB:CC:DD:EE:FF\n"
        "\n"
        "LabNetwork   # inline comment\n"
        "   # full comment line\n"
    )
    got = authz.load_allowlist(str(p))
    assert got == ["aa:bb:cc:dd:ee:ff", "labnetwork"]


def test_load_allowlist_missing_file_returns_empty():
    assert authz.load_allowlist("/definitely/not/here.txt") == []
    assert authz.load_allowlist("") == []
    assert authz.load_allowlist(None) == []


def test_in_scope_matches_allowlist_file(tmp_path):
    p = tmp_path / "allowlist.txt"
    p.write_text("DE:AD:BE:EF:00:01\nLabNet\n")
    cfg = Config()
    cfg.home_networks = []                 # nothing in home_networks
    cfg.allowlist_path = str(p)
    # BSSID from the allowlist.
    assert authz.in_scope("DE:AD:BE:EF:00:01", "", cfg) is True
    # SSID substring from the allowlist.
    assert authz.in_scope("00:00:00:00:00:00", "LabNet-2G", cfg) is True
    # Not listed -> denied.
    assert authz.in_scope("11:22:33:44:55:66", "OtherNet", cfg) is False


# -- Authorizer -------------------------------------------------------------

def test_authorizer_is_authorized_callable_form():
    cfg = Config()
    cfg.home_networks = ["HomeNet"]
    az = authz.Authorizer(cfg)
    assert az.is_authorized("AA:BB:CC:DD:EE:FF", "HomeNet") is True
    assert az.is_authorized("AA:BB:CC:DD:EE:FF", "Stranger") is False


def test_authorizer_require_audit_logs_json_line(tmp_path):
    log_path = tmp_path / "audit.log"
    cfg = Config()
    cfg.home_networks = ["HomeNet"]
    cfg.audit_log = str(log_path)
    az = authz.Authorizer(cfg, clock=lambda: "2026-06-17T12:00:00")

    allowed, reason = az.require("capture", "AA:BB:CC:DD:EE:01", "HomeNet")
    assert allowed is True
    assert isinstance(reason, str) and reason

    denied, reason2 = az.require("deauth", "99:88:77:66:55:44", "StrangerNet")
    assert denied is False
    assert isinstance(reason2, str) and reason2

    lines = log_path.read_text().strip().splitlines()
    assert len(lines) == 2

    rec0 = json.loads(lines[0])
    assert rec0["ts"] == "2026-06-17T12:00:00"
    assert rec0["action"] == "capture"
    assert rec0["bssid"] == "AA:BB:CC:DD:EE:01"
    assert rec0["ssid"] == "HomeNet"
    assert rec0["allowed"] is True
    assert "reason" in rec0
    assert set(rec0) == {"ts", "action", "bssid", "ssid", "allowed", "reason"}

    rec1 = json.loads(lines[1])
    assert rec1["action"] == "deauth"
    assert rec1["allowed"] is False


def test_authorizer_require_never_raises_on_unwritable_audit():
    cfg = Config()
    cfg.home_networks = ["HomeNet"]
    # A path whose parent can't be created -> write fails, must not raise.
    cfg.audit_log = "/proc/cannot/write/here/audit.log"
    az = authz.Authorizer(cfg)
    allowed, reason = az.require("crack", "AA:BB:CC:DD:EE:01", "HomeNet")
    assert allowed is True and isinstance(reason, str)


# -- doctor report ----------------------------------------------------------

def _fake_preflight(tools_present: bool):
    """Build a preflight() stand-in with all tools present/absent."""
    def _pf(cfg):
        return {
            "tools": {name: tools_present for name in preflight_mod.TOOLS},
            "privileges": {
                "is_root": tools_present,
                "has_cap_net_admin": tools_present,
                "can_monitor": tools_present,
            },
            "interface": {"name": "mon0", "exists": tools_present,
                          "wireless": tools_present},
            "wordlist": {"path": "/usr/share/wordlists/rockyou.txt",
                         "exists": tools_present,
                         "size": 1024 * 1024 if tools_present else 0},
            "regdomain": {"available": tools_present,
                          "country": "AU" if tools_present else None,
                          "raw": ""},
        }
    return _pf


def test_doctor_report_sections_present(monkeypatch):
    monkeypatch.setattr(doctor._preflight, "preflight", _fake_preflight(False))
    cfg = Config()
    cfg.home_networks = []
    out = doctor.report(cfg)
    assert isinstance(out, str)
    for header in ("Tools:", "Privileges:", "Interface:", "Wordlist:", "Scope"):
        assert header in out
    assert "You can:" in out


def test_doctor_report_tools_absent_shows_missing(monkeypatch):
    monkeypatch.setattr(doctor._preflight, "preflight", _fake_preflight(False))
    cfg = Config()
    cfg.home_networks = []
    out = doctor.report(cfg)
    # Essential tools absent -> MISS markers + install hints.
    assert doctor.MISS in out
    assert "install hashcat" in out
    # Empty scope -> deny-by-default warning + capability summary fallback.
    assert "deny by default" in out
    assert "nothing yet" in out


def test_doctor_report_full_stack_can_do_everything(monkeypatch, tmp_path):
    monkeypatch.setattr(doctor._preflight, "preflight", _fake_preflight(True))
    cfg = Config()
    cfg.home_networks = ["HomeNet"]
    out = doctor.report(cfg)
    assert doctor.OK in out
    # Everything present + scope set -> all three capabilities offered.
    assert "[passive scan]" in out
    assert "[capture]" in out
    assert "[crack]" in out


def test_doctor_report_uses_allowlist_for_scope(monkeypatch, tmp_path):
    p = tmp_path / "allowlist.txt"
    p.write_text("AA:BB:CC:DD:EE:FF\n")
    monkeypatch.setattr(doctor._preflight, "preflight", _fake_preflight(True))
    cfg = Config()
    cfg.home_networks = []
    cfg.allowlist_path = str(p)
    out = doctor.report(cfg)
    assert "allowlist" in out
    assert "[capture]" in out      # scope satisfied via the allowlist file


def test_doctor_run_prints(monkeypatch, capsys):
    monkeypatch.setattr(doctor._preflight, "preflight", _fake_preflight(False))
    cfg = Config()
    doctor.run(cfg)
    captured = capsys.readouterr()
    assert "Flippergotchi doctor" in captured.out


# -- preflight probes are read-only + never raise ---------------------------

def test_preflight_aggregate_shape_no_hardware():
    cfg = Config()
    pf = preflight_mod.preflight(cfg)
    assert set(pf) == {"tools", "privileges", "interface", "wordlist", "regdomain"}
    assert set(pf["privileges"]) == {"is_root", "has_cap_net_admin", "can_monitor"}
    assert set(pf["interface"]) == {"name", "exists", "wireless"}
    assert set(pf["wordlist"]) == {"path", "exists", "size"}
    # All tool values are bools.
    assert all(isinstance(v, bool) for v in pf["tools"].values())


def test_check_tools_all_absent(monkeypatch):
    monkeypatch.setattr(preflight_mod.shutil, "which", lambda name: None)
    tools = preflight_mod.check_tools()
    assert tools and all(v is False for v in tools.values())


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
