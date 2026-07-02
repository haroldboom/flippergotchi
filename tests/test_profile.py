"""The read-only `profile` summary command.

Hermetic (tmp paths, sim mode): seeds a few stores, then asserts cmd_profile
prints the key lines and -- crucially -- mutates NOTHING (no rolls/grants/saves).
"""
from __future__ import annotations

import dataclasses
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flippergotchi.config import Config
from flippergotchi import commands, persistence
from flippergotchi.game.bestiary import Bestiary
from flippergotchi.game import monsters
from flippergotchi.game.shop import Wallet
from flippergotchi.pet.state import PetState


def _cfg(tmp_path):
    cfg = Config()
    cfg.simulate = True
    cfg.tui = False
    cfg.scan_bluetooth = False
    for f in dataclasses.fields(cfg):
        v = getattr(cfg, f.name)
        if isinstance(v, str) and (v.startswith("~/.flippergotchi")
                                   or v.startswith("/tmp/")):
            setattr(cfg, f.name, str(tmp_path / f.name))
    return cfg


def test_cmd_profile_prints_key_lines(tmp_path, capsys):
    cfg = _cfg(tmp_path)
    state = PetState(name="Sharkey", level=7)
    state.stage = "teen"
    persistence.save(cfg.state_path, state)
    w = Wallet(cfg.wallet_path)
    w.earn(123)
    w.save()

    commands.cmd_profile(cfg)
    out = capsys.readouterr().out

    assert "PROFILE" in out
    assert "Sharkey" in out
    assert "Lv7" in out
    assert "NORMAL" in out           # mode line
    assert "scrap: 123" in out
    assert "badges:" in out
    assert "quests:" in out
    assert "streak:" in out
    assert "species:" in out


def test_cmd_profile_runs_with_empty_stores(tmp_path, capsys):
    cfg = _cfg(tmp_path)
    persistence.save(cfg.state_path, PetState(name="T"))
    commands.cmd_profile(cfg)  # no other stores on disk -> must not raise
    out = capsys.readouterr().out
    assert "scrap: 0" in out
    assert "species: 0/" in out


def test_cmd_profile_shows_hardcore_mode(tmp_path, capsys):
    cfg = _cfg(tmp_path)
    state = PetState(name="T")
    state.hardcore = True
    persistence.save(cfg.state_path, state)
    commands.cmd_profile(cfg)
    assert "HARDCORE" in capsys.readouterr().out


def test_cmd_profile_counts_shinies_and_bestiary(tmp_path, capsys):
    cfg = _cfg(tmp_path)
    persistence.save(cfg.state_path, PetState(name="T"))
    dex = Bestiary(cfg.bestiary_path)
    m = monsters.from_ap({"type": "ap", "bssid": "AA:BB:CC:00:11:22",
                          "ssid": "HomeNet", "encryption": "wpa2",
                          "band": "2.4GHz", "clients": 1, "signal": -40})
    m.captured = True
    m.shiny = True
    dex.add(m)
    dex.save()

    commands.cmd_profile(cfg)
    out = capsys.readouterr().out
    assert "shinies: 1" in out
    assert "species: 1/" in out


def test_cmd_profile_is_read_only(tmp_path):
    """Viewing the profile must not create/roll/grant anything."""
    cfg = _cfg(tmp_path)
    persistence.save(cfg.state_path, PetState(name="T"))
    commands.cmd_profile(cfg)
    # the view loads stores read-only and never saves them, so no quest/wallet/
    # achievement files are written just by looking.
    assert not (tmp_path / "quests_path").exists()
    assert not (tmp_path / "wallet_path").exists()
    assert not (tmp_path / "achievements_path").exists()
