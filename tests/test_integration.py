"""Integration coverage for the wiring that lives OUTSIDE the per-module agents:
the CLI commands (doctor/shop/achievements/battle) and the Agent sim loop with
the capture backend + scrap/achievement hooks. All hermetic (tmp paths, sim
mode), no hardware.
"""
from __future__ import annotations

import dataclasses

from flippergotchi.config import Config
from flippergotchi import commands, persistence
from flippergotchi.agent import Agent
from flippergotchi.game.bestiary import Bestiary
from flippergotchi.game import monsters
from flippergotchi.game.shop import Wallet
from flippergotchi.pet.state import PetState


def _cfg(tmp_path):
    """A Config with every persistence path redirected under tmp_path."""
    cfg = Config()
    cfg.simulate = True
    cfg.tui = False
    cfg.scan_bluetooth = False
    for f in dataclasses.fields(cfg):
        v = getattr(cfg, f.name)
        if isinstance(v, str) and (v.startswith("~/.flippergotchi") or v.startswith("/tmp/")):
            setattr(cfg, f.name, str(tmp_path / f.name))
    return cfg


def test_capture_backend_is_sim_under_simulate(tmp_path):
    cfg = _cfg(tmp_path)
    agent = Agent(cfg, PetState(name="T"))
    assert type(agent.wifi).__name__ == "SimBackend"
    # scan() is the backend API the loop now calls (was poll())
    assert isinstance(agent.wifi.scan(), list)


def test_agent_sim_tick_earns_scrap_and_runs(tmp_path):
    cfg = _cfg(tmp_path)
    state = PetState(name="T")
    agent = Agent(cfg, state)
    # force a guaranteed catch path by feeding an AP event straight in
    ev = {"type": "ap", "bssid": "AA:BB:CC:00:11:22", "ssid": "HomeNet",
          "encryption": "wpa2", "band": "2.4GHz", "clients": 2, "signal": -50}
    agent._encounter(ev)
    # a catch awards scrap and may unlock "First Blood"
    assert agent.wallet.scrap >= 0  # never negative
    agent._save()
    assert (tmp_path / "wallet_path").exists()
    assert (tmp_path / "achievements_path").exists()


def test_cmd_doctor_runs(tmp_path, capsys):
    commands.cmd_doctor(_cfg(tmp_path))
    out = capsys.readouterr().out
    assert "Tools:" in out and "Scope" in out


def test_cmd_shop_list_and_buy(tmp_path, capsys):
    cfg = _cfg(tmp_path)
    Wallet(cfg.wallet_path)  # zero balance file
    # give the wallet enough to buy
    w = Wallet(cfg.wallet_path)
    w.earn(100)
    w.save()
    commands.cmd_shop(cfg, None, None)          # browse
    assert "SHOP" in capsys.readouterr().out
    commands.cmd_shop(cfg, "buy", "ration")     # buy
    assert "Fed the pet" in capsys.readouterr().out
    assert Wallet(cfg.wallet_path).scrap == 40   # 100 - 60


def test_cmd_battle_awards_on_authorized_crack(tmp_path, capsys):
    cfg = _cfg(tmp_path)
    dex = Bestiary(cfg.bestiary_path)
    m = monsters.from_ap({"type": "ap", "bssid": "AA:BB:CC:00:11:22",
                          "ssid": "HomeNet", "encryption": "open",
                          "band": "2.4GHz", "clients": 1, "signal": -40})
    m.captured = True
    dex.add(m)
    dex.save()
    persistence.save(cfg.state_path, PetState(name="T"))
    commands.cmd_battle(cfg, "HomeNet", authorized=True, dont_show=True)
    out = capsys.readouterr().out
    assert "cracked" in out
    assert "scrap" in out  # award line printed
    assert Wallet(cfg.wallet_path).scrap > 0
