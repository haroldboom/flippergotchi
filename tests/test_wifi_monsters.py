"""WiFi monsters by AP brand, WEP/WPA1 legendaries, WEP aircrack path, and the
on-the-fly field battle for weak/legacy networks."""
from __future__ import annotations

import dataclasses
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from flippergotchi.config import Config
from flippergotchi.agent import Agent
from flippergotchi.game import monsters
from flippergotchi.game import cracking as cracking_mod
from flippergotchi.game.cracking import LocalCracker
from flippergotchi.game.bestiary import Bestiary
from flippergotchi.pet.state import PetState


def _ap(ssid, enc="wpa2", bssid="AA:BB:CC:00:11:22", clients=1, band="2.4GHz"):
    return {"type": "ap", "ssid": ssid, "bssid": bssid, "encryption": enc,
            "band": band, "clients": clients, "signal": -55}


# -- species by brand -------------------------------------------------------
def test_wpa2_species_by_vendor():
    assert monsters.from_ap(_ap("NETGEAR")).species == "Gnashgear"
    assert monsters.from_ap(_ap("Linksys")).species == "Synksquid"
    assert monsters.from_ap(_ap("TP-LINK_2G")).species == "Mantalink"
    assert monsters.from_ap(_ap("xfinitywifi")).species == "Telewyrm"      # ISP
    assert monsters.from_ap(_ap("MyHiddenNet")).species == "Crypterion"     # unknown


def test_vendor_from_oui_when_ssid_is_plain():
    m = monsters.from_ap(_ap("NoBrandHere", bssid="9C:3D:CF:11:22:33"))
    assert m.vendor == "Netgear" and m.species == "Gnashgear"


def test_wep_and_wpa1_are_legendaries():
    wep = monsters.from_ap(_ap("NETGEAR", enc="wep"))
    wpa = monsters.from_ap(_ap("Linksys", enc="wpa"))
    assert wep.species == "Wepwraith" and wep.rarity == "legendary"
    assert wpa.species == "Wparchon" and wpa.rarity == "legendary"
    # legendary overrides the vendor species
    assert wep.species != "Gnashgear"


# -- WEP aircrack-ng path ---------------------------------------------------
def test_parse_wep_key():
    out = "Decrypted correctly: 100%\n   KEY FOUND! [ 1A:2B:3C:4D:5E ]\n"
    assert LocalCracker._parse_wep_key(out) == "1A:2B:3C:4D:5E"


def test_wep_crack_uses_aircrack(monkeypatch, tmp_path):
    cap = tmp_path / "ivs.cap"
    cap.write_bytes(b"\x00" * 32)
    cfg = Config()  # simulate False
    monkeypatch.setattr(cracking_mod.shutil, "which",
                        lambda name: "/usr/bin/aircrack-ng" if name == "aircrack-ng" else None)
    monkeypatch.setattr(cracking_mod.subprocess, "run",
                        lambda *a, **k: types.SimpleNamespace(
                            stdout="KEY FOUND! [ AA:BB:CC:DD:EE ]", returncode=0))
    m = monsters.from_ap(_ap("NETGEAR", enc="wep"))
    res = LocalCracker(cfg).crack(m, str(cap))
    assert res.result == "cracked" and res.via == "aircrack-ng"
    assert res.key == "AA:BB:CC:DD:EE" and res.mode == "wep"


# -- on-the-fly field battle ------------------------------------------------
def _agent(tmp_path, **cfgkw):
    cfg = Config()
    cfg.simulate = True
    cfg.tui = False
    cfg.scan_bluetooth = False
    for f in dataclasses.fields(cfg):
        v = getattr(cfg, f.name)
        if isinstance(v, str) and (v.startswith("~/.flippergotchi") or v.startswith("/tmp/")):
            setattr(cfg, f.name, str(tmp_path / f.name))
    for k, v in cfgkw.items():
        setattr(cfg, k, v)
    return Agent(cfg, PetState(name="T"))


def _force_catch(monkeypatch, a):
    """Make the encounter deterministically CAUGHT (capture is otherwise a roll)."""
    import flippergotchi.game.encounter as enc_mod
    monkeypatch.setattr(enc_mod, "capture_chance", lambda m: 1.0)
    monkeypatch.setattr(a, "_choose", lambda m: "capture")


def test_open_network_field_battle(tmp_path, monkeypatch):
    a = _agent(tmp_path, home_networks=["FreeWifi"])
    _force_catch(monkeypatch, a)
    a._encounter(_ap("FreeWifi", enc="open", bssid="AA:BB:CC:00:00:01"))
    m = a.dex.get("AA:BB:CC:00:00:01")
    assert m is not None and m.defeated and m.key == "(open)"
    assert a.ledger.counts()["win"] == 1


def test_wep_field_battle_in_scope(tmp_path, monkeypatch):
    a = _agent(tmp_path, home_networks=["OldRouter"])
    _force_catch(monkeypatch, a)
    a._prefs["hide_fieldcrack_warning"] = True          # consent already given
    monkeypatch.setattr(cracking_mod.random, "random", lambda: 0.0)  # sim crack lands
    a._encounter(_ap("OldRouter", enc="wep", bssid="AA:BB:CC:00:00:02"))
    m = a.dex.get("AA:BB:CC:00:00:02")
    assert m.species == "Wepwraith"
    # sim crack of a trivial WEP almost always lands -> defeated + a ledger row
    assert m.defeated and a.ledger.counts()["win"] >= 1


def test_wep_not_cracked_without_consent(tmp_path, monkeypatch):
    # in scope + caught, but the on-the-fly crack consent hasn't been given and
    # there's no TTY to ask -> captured, NOT auto-cracked.
    a = _agent(tmp_path, home_networks=["OldRouter"])
    _force_catch(monkeypatch, a)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    a._encounter(_ap("OldRouter", enc="wep", bssid="AA:BB:CC:00:00:05"))
    m = a.dex.get("AA:BB:CC:00:00:05")
    assert m is not None and m.captured and not m.defeated
    assert a.ledger.counts()["win"] == 0


def test_open_needs_no_consent(tmp_path, monkeypatch):
    # open networks just associate (no crack) -> no consent gate
    a = _agent(tmp_path, home_networks=["FreeWifi"])
    _force_catch(monkeypatch, a)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    a._encounter(_ap("FreeWifi", enc="open", bssid="AA:BB:CC:00:00:06"))
    assert a.dex.get("AA:BB:CC:00:00:06").defeated


def test_wpa2_is_not_field_cracked(tmp_path, monkeypatch):
    a = _agent(tmp_path, home_networks=["NETGEAR"])
    _force_catch(monkeypatch, a)
    a._encounter(_ap("NETGEAR", enc="wpa2", bssid="AA:BB:CC:00:00:03"))
    m = a.dex.get("AA:BB:CC:00:00:03")
    # WPA2 is captured but NOT auto-cracked in the field (no ledger win)
    assert m is not None and not m.defeated
    assert a.ledger.counts()["win"] == 0


def test_out_of_scope_weak_network_not_cracked(tmp_path, monkeypatch):
    a = _agent(tmp_path, home_networks=[])   # deny-by-default
    _force_catch(monkeypatch, a)
    a._encounter(_ap("SomeoneElse", enc="wep", bssid="AA:BB:CC:00:00:04"))
    m = a.dex.get("AA:BB:CC:00:00:04")
    assert m is not None and not m.defeated     # refused -- not in your scope
    assert a.ledger.counts()["win"] == 0
