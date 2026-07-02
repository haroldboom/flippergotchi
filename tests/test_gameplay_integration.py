"""Integration coverage for the gameplay-update wiring the INTEGRATOR added to
the loop: OPEN-vs-real-crack economy, the pet's voice at payoffs, auto-duels,
energy-sleep, weighted hardcore death, element-from-config, skin persistence
and once-only BLE recon. All hermetic (tmp paths, sim mode), no hardware.
"""
from __future__ import annotations

import dataclasses
import random

import pytest

from flippergotchi.config import Config
from flippergotchi import persistence
from flippergotchi.agent import Agent
from flippergotchi.game import monsters
from flippergotchi.game import shop as shop_mod
from flippergotchi.pet import mechanics
from flippergotchi.pet.state import PetState


@pytest.fixture(autouse=True)
def _preserve_rng():
    """These tests seed the global RNG for determinism; snapshot + restore it so
    they never perturb the RNG ordering other test modules rely on."""
    state = random.getstate()
    yield
    random.setstate(state)


def _cfg(tmp_path):
    """A Config with every persistence path redirected under tmp_path."""
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


def _spy_speak(agent):
    """Record every speak() event key while still running the real call."""
    calls = []
    orig = agent.speak

    def rec(key, arg="", sub=""):
        calls.append(key)
        return orig(key, arg, sub)

    agent.speak = rec
    return calls


def _open_ev():
    return {"type": "ap", "bssid": "AA:BB:CC:00:11:22", "ssid": "FreeWiFi",
            "encryption": "open", "band": "2.4GHz", "clients": 1, "signal": -40}


def _wep_ev():
    return {"type": "ap", "bssid": "DD:EE:FF:00:11:22", "ssid": "OldRouter",
            "encryption": "wep", "band": "2.4GHz", "clients": 2, "signal": -50}


# --- task 1: OPEN pays 18 & no loot; WEP still pays 120 + loot --------------

def test_open_field_battle_pays_18_no_loot(tmp_path):
    cfg = _cfg(tmp_path)
    agent = Agent(cfg, PetState(name="T"))
    m = monsters.from_ap(_open_ev())
    before, before_items = agent.wallet.scrap, len(agent.inv.items)
    agent._field_battle(m)
    # OPEN pays catch-tier (18) and NOTHING more: no crack (120), no loot roll
    assert agent.wallet.scrap - before == shop_mod.scrap_for_open()
    assert len(agent.inv.items) == before_items


def test_wep_pays_120_and_loot(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.manual = True                     # manual pick satisfies crack scope-gate
    agent = Agent(cfg, PetState(name="T"))
    agent._prefs["hide_fieldcrack_warning"] = True   # field-crack consent granted
    before_items = len(agent.inv.items)
    random.seed(1)
    ev = _wep_ev()
    # Force a near-certain sim crack (p = 1 - defense/100).
    m = monsters.from_ap(ev)
    m.defense = 0
    # drive the crack path directly with the low-defense monster
    agent._field_battle(m)
    assert m.defeated is True
    assert agent.wallet.scrap >= shop_mod.scrap_for_crack()   # 120+
    assert len(agent.inv.items) == before_items + 1           # loot rolled


# --- task 2: the pet gets a voice at payoffs -------------------------------

def test_speak_fires_on_crack(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.manual = True
    agent = Agent(cfg, PetState(name="T"))
    agent._prefs["hide_fieldcrack_warning"] = True
    calls = _spy_speak(agent)
    random.seed(1)
    m = monsters.from_ap(_wep_ev())
    m.defense = 0
    agent._field_battle(m)
    assert "cracked" in calls


def test_speak_fires_on_quest(tmp_path):
    cfg = _cfg(tmp_path)
    agent = Agent(cfg, PetState(name="T"))
    calls = _spy_speak(agent)
    # roll today's quests, then drive an ACTIVE metric to completion
    agent.quests.roll("2026-07-02")
    q = agent.quests.active()[0]
    agent._quest(q.metric, q.target)
    assert "quest_done" in calls


def test_speak_fires_on_badge(tmp_path):
    cfg = _cfg(tmp_path)
    agent = Agent(cfg, PetState(name="T"))
    calls = _spy_speak(agent)
    random.seed(3)                 # deterministic capture (not an escape)
    agent._encounter(_open_ev())   # First Blood unlocks on the first catch
    assert "caught" in calls
    assert "badge" in calls


def test_speak_fires_on_shiny(tmp_path):
    cfg = _cfg(tmp_path)
    agent = Agent(cfg, PetState(name="T"))
    calls = _spy_speak(agent)
    # find a bssid whose stable shiny hash is True, then catch it
    ev = None
    for i in range(2000):
        bssid = f"AA:BB:CC:{i // 256:02X}:{i % 256:02X}:00"
        m = monsters.from_ap({"type": "ap", "bssid": bssid, "ssid": "Sparkle",
                              "encryption": "wpa2", "band": "2.4GHz",
                              "clients": 1, "signal": -40})
        if getattr(m, "shiny", False):
            ev = {"type": "ap", "bssid": bssid, "ssid": "Sparkle",
                  "encryption": "wpa2", "band": "2.4GHz", "clients": 1,
                  "signal": -40}
            break
    assert ev is not None, "no shiny bssid found"
    agent._encounter(ev)
    assert "shiny" in calls


# --- task 3: auto-duel triggers and applies its outcome --------------------

def test_auto_duel_triggers_and_applies(tmp_path, capsys):
    cfg = _cfg(tmp_path)
    cfg.auto_duel_chance = 1.0
    cfg.auto_duel_cooldown = 0
    state = PetState(name="T", level=30, handshakes=20)
    agent = Agent(cfg, state)
    agent._peers["11:22:33:44:55:66"] = {
        "name": "Rival", "addr": "11:22:33:44:55:66", "level": 2,
        "handshakes": 8, "gear_power": 0, "element": "Tide"}
    random.seed(3)
    peer_before = agent._peers["11:22:33:44:55:66"]["handshakes"]
    agent._maybe_duel()
    out = capsys.readouterr().out
    assert "[duel]" in out                       # outcome narrated
    peer_after = agent._peers["11:22:33:44:55:66"]["handshakes"]
    # a strong player vs a weak peer should win: duel_wins + drained peer pool
    assert state.duel_wins == 1
    assert peer_after < peer_before


# --- task 5: maybe_sleep runs every tick -----------------------------------

def test_tick_calls_maybe_sleep(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    agent = Agent(cfg, PetState(name="T"))
    seen = []
    real = mechanics.maybe_sleep
    monkeypatch.setattr(mechanics, "maybe_sleep",
                        lambda s, c: seen.append(True) or real(s, c))
    agent.tick(0.1)
    assert seen == [True]


# --- task 6: hardcore death renders an epitaph and never blocks off-tty -----

def test_hardcore_death_renders_epitaph_no_block(tmp_path, capsys):
    cfg = _cfg(tmp_path)
    state = PetState(name="Sharky", hardcore=True, level=9, handshakes=12)
    agent = Agent(cfg, state)
    agent._hardcore_death()   # pytest stdin is not a tty -> must not block
    out = capsys.readouterr().out
    assert "HERE LIES" in out
    assert "Sharky" in out
    assert agent.state.level == 1   # reborn as a fresh egg


# --- task 7: element flows from config -------------------------------------

def test_element_flows_from_config(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.element = "Spark"
    agent = Agent(cfg, PetState(name="T"))
    assert agent.state.element == "Spark"


# --- task 9: skins persist across a reload ---------------------------------

def test_skins_persist(tmp_path):
    cfg = _cfg(tmp_path)
    state = PetState(name="T")
    state.skins = ["skin_goldfin"]
    persistence.save(cfg.state_path, state)
    reloaded = persistence.load(cfg.state_path)
    assert reloaded.skins == ["skin_goldfin"]


# --- task 10: BLE recon reward pays only once ------------------------------

def test_ble_recon_pays_once(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.scan_bluetooth = True
    agent = Agent(cfg, PetState(name="T"))
    ev = {"type": "ble", "addr": "C0:FF:EE:00:00:01", "name": "Fitbit",
          "device_class": "wearable", "connectable": True, "rssi": -55}
    m = monsters.from_ble(ev)
    agent._tame_ble(m, ev)
    first = agent.wallet.scrap
    assert first > 0
    assert m.last_result == "interrogated"
    agent._tame_ble(m, ev)   # re-sighting must NOT re-farm
    assert agent.wallet.scrap == first
