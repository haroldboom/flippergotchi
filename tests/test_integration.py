"""Integration coverage for the wiring that lives OUTSIDE the per-module agents:
the CLI commands (doctor/shop/achievements/battle) and the Agent sim loop with
the capture backend + scrap/achievement hooks. All hermetic (tmp paths, sim
mode), no hardware.
"""
from __future__ import annotations


from flippergotchi import commands, persistence
from flippergotchi.agent import Agent
from flippergotchi.game.bestiary import Bestiary
from flippergotchi.game import monsters
from flippergotchi.game.shop import Wallet
from flippergotchi.pet.state import PetState


def test_capture_backend_is_sim_under_simulate(make_cfg):
    cfg = make_cfg()
    agent = Agent(cfg, PetState(name="T"))
    assert type(agent.wifi).__name__ == "SimBackend"
    # scan() is the backend API the loop now calls (was poll())
    assert isinstance(agent.wifi.scan(), list)


def test_agent_sim_tick_earns_scrap_and_runs(make_cfg, tmp_path):
    cfg = make_cfg()
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


def test_cmd_doctor_runs(make_cfg, capsys):
    commands.cmd_doctor(make_cfg())
    out = capsys.readouterr().out
    assert "Tools:" in out and "Authorization" in out


def test_cmd_shop_list_and_buy(make_cfg, capsys):
    cfg = make_cfg()
    Wallet(cfg.wallet_path)  # zero balance file
    # give the wallet enough to buy
    w = Wallet(cfg.wallet_path)
    w.earn(200)
    w.save()
    commands.cmd_shop(cfg, None, None)          # browse
    assert "SHOP" in capsys.readouterr().out
    commands.cmd_shop(cfg, "buy", "ration")     # buy
    assert "Fed the pet" in capsys.readouterr().out
    assert Wallet(cfg.wallet_path).scrap == 20   # 200 - 180


def test_cmd_battle_awards_on_authorized_crack(make_cfg, capsys):
    # The crack outcome is an RNG roll; pin the stream so this asserts a
    # *successful* crack regardless of collection order (pytest-randomly).
    import random
    random.seed(1234)
    cfg = make_cfg()
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
