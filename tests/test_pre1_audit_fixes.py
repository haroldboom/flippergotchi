"""Regression tests for the pre-1.0 audit fixes.

Covers the confirmed findings from the read-only audit:
  * WiFi re-encounter persists crack/capture state (canonical-object fix)
  * the live agent loop's per-target deauth gate (no mass auto-deauth)
  * tick() crash-guard + the previously-untested main loop / hardcore-death /
    evolution-event paths
  * tolerant JSON loads (one bad row never wipes a whole store / crashes)
  * quest streak adjacency, the daily-scrap economy band, the duel-farm guard
  * TrackerLog safety-check hardening, and the flipctl HP/damage thresholds.

All hermetic: tmp paths + sim mode, no real radio/clock dependence.
"""
from __future__ import annotations

import dataclasses
import json
import random

import pytest

from flippergotchi.agent import Agent
from flippergotchi.config import Config
from flippergotchi.pet.state import PetState
from flippergotchi.pet import mechanics


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


BSSID = "AA:BB:CC:DD:EE:01"


# --- WiFi re-encounter persistence (HIGH) ----------------------------------

def test_bestiary_reencounter_merges_and_returns_canonical(tmp_path):
    from flippergotchi.game.bestiary import Bestiary
    from flippergotchi.game import monsters

    dex = Bestiary(str(tmp_path / "dex.json"))
    ev = {"type": "ap", "bssid": BSSID, "ssid": "N", "encryption": "open"}
    assert dex.add(monsters.from_ap(ev)) is True

    # re-sight the same AP; the fresh throwaway carries a new capture_path
    m2 = monsters.from_ap(ev)
    m2.capture_path = "/tmp/hs.pcap"
    assert dex.add(m2) is False                # not newly discovered
    canon = dex.get(BSSID)
    assert canon.capture_path == "/tmp/hs.pcap"   # capture_path merged in

    # mutating the canonical object (as agent._encounter now does) persists
    canon.defeated, canon.key = True, "secret"
    dex.save()
    again = Bestiary(str(tmp_path / "dex.json")).get(BSSID)
    assert again.defeated and again.key == "secret"
    assert again.capture_path == "/tmp/hs.pcap"


def test_agent_encounter_persists_crack_on_reencounter(tmp_path, monkeypatch):
    import flippergotchi.game.encounter as enc
    monkeypatch.setattr(enc, "auto_choice", lambda m, rng=None: "capture")
    monkeypatch.setattr(enc.Encounter, "choose",
                        lambda self, action, rng=None: self.resolve_capture(True))

    cfg = _cfg(tmp_path)
    agent = Agent(cfg, PetState(name="P"))
    ev = {"type": "ap", "bssid": BSSID, "ssid": "OpenNet",
          "encryption": "open", "band": "2.4GHz"}

    agent._encounter(ev)
    m = agent.dex.get(BSSID)
    assert m is not None and m.defeated and m.key == "(open)"

    # re-encounter after the cooldown: the stored monster stays cracked, and the
    # mutation lands on the canonical object (not a discarded throwaway).
    agent._tick_i += cfg.encounter_cooldown + 1
    agent._encounter(ev)
    assert agent.dex.get(BSSID).defeated


# --- per-target deauth gate (HIGH, safety) ---------------------------------

def test_capture_gate_is_per_target_not_global(tmp_path):
    cfg = _cfg(tmp_path)
    agent = Agent(cfg, PetState(name="P"))

    # no consent -> never active, regardless of target
    assert agent._capture_authorized(BSSID, "Any") is False

    agent._prefs["hide_fieldcrack_warning"] = True       # session consent given
    # auto mode + out of scope -> still passive (NOT mass-deauth)
    cfg.manual = False
    cfg.home_networks = []
    assert agent._capture_authorized(BSSID, "Stranger") is False
    # manual mode = the player picked this AP with a button -> allowed
    cfg.manual = True
    assert agent._capture_authorized(BSSID, "Stranger") is True
    # auto mode but the AP is in the optional authorized scope -> allowed
    cfg.manual = False
    cfg.home_networks = ["MyHome"]
    assert agent._capture_authorized(BSSID, "MyHome") is True
    assert agent._capture_authorized(BSSID, "Stranger") is False


# --- tick() crash-guard + main-loop coverage (HIGH) ------------------------

def test_tick_end_to_end_runs_and_decays(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.time_scale = 100000.0            # exaggerate decay so it's measurable
    agent = Agent(cfg, PetState(name="Loop", hunger=10.0))
    start_hunger = agent.state.hunger
    for _ in range(15):
        agent.tick(1.0)
    assert agent._tick_i == 15
    assert agent.state.hunger > start_hunger     # time passed -> got hungrier
    agent._save()                                # the periodic save path works


def test_tick_survives_a_raising_scan(tmp_path):
    cfg = _cfg(tmp_path)
    agent = Agent(cfg, PetState(name="Hardy"))

    def boom():
        raise RuntimeError("malformed AP from a real radio")
    agent.wifi.scan = boom                       # type: ignore[assignment]
    logs = []
    agent.log = lambda m: logs.append(m)

    agent.tick(1.0)                              # must NOT raise
    assert agent._tick_i == 1
    assert any("tick step failed" in m for m in logs)


def test_hardcore_death_reborn_egg(tmp_path):
    cfg = _cfg(tmp_path)
    agent = Agent(cfg, PetState(name="Doomed", hardcore=True,
                                hunger=100.0, health=0.0, level=12))
    # Death now has runway: at 0 HP the pet survives a fixed number of faint
    # ticks (mechanics.FAINT_DEATH_GRACE_TICKS) before is_dead flips, giving the
    # player warning frames. Drive past the grace window, then it reborns.
    assert mechanics.is_dead(agent.state) is False       # not an instant cliff
    for _ in range(mechanics.FAINT_DEATH_GRACE_TICKS + 1):
        agent.tick(1.0)
    assert agent.state.stage == "egg"
    assert agent.state.level == 1
    assert agent.state.name == "Doomed"
    assert agent.state.hardcore is True
    # the reborn egg was persisted
    from flippergotchi import persistence
    on_disk = persistence.load(cfg.state_path)
    assert on_disk.stage == "egg" and on_disk.hardcore is True


def test_evolution_event_is_emitted(tmp_path):
    cfg = Config()
    state = PetState(name="Evo", level=1, stage="egg")
    evts = mechanics.grant_xp(state, cfg.base_xp + 1, cfg)   # cross level 1->2
    assert any(e.get("evolved_to") == "hatchling" for e in evts)
    assert state.stage == "hatchling"


# --- agent BLE sim path (MEDIUM coverage gap) ------------------------------

class _FakeScanner:
    mode = "sim"

    def __init__(self, events):
        self._events = events

    def poll(self):
        return list(self._events)

    def enumerate(self, _id):
        return {"services": ["battery_service", "device_information"],
                "characteristics": 4}


def test_spawn_ble_collects_tames_and_alerts(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    agent = Agent(cfg, PetState(name="BT"))
    tracker_ev = {"type": "ble", "addr": "11:22:33:44:55:66",
                  "device_class": "tracker", "name": "AirThing",
                  "rssi": -50, "connectable": True}
    agent.ble = _FakeScanner([tracker_ev])
    # force the safety alert branch (real time can't span the window in a test)
    monkeypatch.setattr(agent.trackers, "should_alert", lambda *a, **k: True)
    logs = []
    agent.log = lambda m: logs.append(m)

    agent._spawn_ble()

    assert agent.dex.get("11:22:33:44:55:66") is not None     # collected
    assert "11:22:33:44:55:66" in agent.trackers._seen        # tracker logged
    assert any("[ALERT]" in m for m in logs)                  # safety alert fired
    assert any("interrogated" in m for m in logs)             # GATT tame ran


def test_note_peer_registers_a_duel_target(tmp_path):
    cfg = _cfg(tmp_path)
    agent = Agent(cfg, PetState(name="Me"))
    agent._note_peer({"type": "peer", "addr": "AA:11:BB:22:CC:33",
                      "name": "Rival", "level": 5, "handshakes": 12})
    assert "AA:11:BB:22:CC:33" in agent._peers
    assert agent._peers["AA:11:BB:22:CC:33"]["name"] == "Rival"


def test_forage_is_economy_only_never_cracks(tmp_path):
    import random as _r
    cfg = _cfg(tmp_path)
    # hunger below the auto-eat line -> food is STASHED, so the larder grows
    agent = Agent(cfg, PetState(name="W", hunger=30.0, health=80.0, satiety=100.0))
    _r.seed(7)
    grew = False
    for _ in range(60):
        before = agent.larder.total() + len(agent.inv.items)
        agent._forage(800.0)
        if agent.larder.total() + len(agent.inv.items) > before:
            grew = True
    assert grew                                     # produced food/gear (economy)
    # foraging (incl. the satiety gear-luck multiplier) must never touch cracking
    assert all(not m.defeated for m in agent.dex.all())


def test_home_check_prompts_once(tmp_path):
    from flippergotchi.game import monsters
    cfg = _cfg(tmp_path)
    cfg.home_networks = ["MyHome"]
    agent = Agent(cfg, PetState(name="Me"))
    # a captured, not-yet-battled WiFi monster makes the "ready to battle" prompt fire
    m = monsters.from_ap({"type": "ap", "bssid": BSSID, "ssid": "x",
                          "encryption": "wpa2"})
    m.captured = True
    agent.dex.add(m)
    agent._visible = ["MyHome-5G"]
    logs = []
    agent.log = lambda s: logs.append(s)

    agent._home_check()
    agent._home_check()                             # still "home" -> must not re-fire
    assert sum(1 for s in logs if "[home]" in s) == 1


# --- tolerant JSON loads (HIGH) --------------------------------------------

def test_bestiary_skips_one_bad_row(tmp_path):
    from flippergotchi.game.bestiary import Bestiary
    from flippergotchi.game import monsters
    good = monsters.from_ap({"type": "ap", "bssid": BSSID, "ssid": "ok",
                             "encryption": "open"})
    p = tmp_path / "dex.json"
    p.write_text(json.dumps({BSSID: good.to_dict(),
                             "BAD": {"id": "BAD"}}))      # missing required fields
    dex = Bestiary(str(p))
    assert dex.get(BSSID) is not None                    # good row survived
    assert "BAD" not in dex.monsters                     # bad row skipped, no wipe


def test_inventory_skips_one_bad_row(tmp_path):
    from flippergotchi.game import equipment
    good = equipment.roll_item()
    p = tmp_path / "inv.json"
    p.write_text(json.dumps({"items": [good.to_dict(), {"oops": 1}],
                             "equipped": {}}))
    inv = equipment.Inventory(str(p))
    assert good.id in inv.items and len(inv.items) == 1


def test_questlog_skips_one_bad_row(tmp_path):
    from flippergotchi.game.quests import QuestLog, Quest
    q = Quest(id="x", description="d", metric="catches", target=1)
    p = tmp_path / "quests.json"
    p.write_text(json.dumps({"schema_version": 3,
                             "quests": [q.to_dict(), {"nope": True}],
                             "weeklies": []}))
    log = QuestLog(str(p))
    assert len(log.quests) == 1 and log.quests[0].id == "x"


def test_ledger_tolerates_non_list_and_bad_rows(tmp_path):
    from flippergotchi.game.ledger import Ledger
    p = tmp_path / "ledger.json"
    p.write_text(json.dumps({"not": "a list"}))          # wrong top-level type
    assert Ledger(str(p)).counts() == {"win": 0, "loss": 0, "escalate": 0}

    p.write_text(json.dumps([{"result": "win"}, "garbage", {"no_result": 1}]))
    led = Ledger(str(p))
    assert led.counts()["win"] == 1                      # bad rows ignored


def test_prefs_non_dict_degrades_to_empty(tmp_path):
    from flippergotchi import prefs
    p = tmp_path / "prefs.json"
    p.write_text(json.dumps(["a", "list", "not", "a", "dict"]))
    assert prefs.load(str(p)) == {}


# --- quest streak adjacency (MEDIUM) ---------------------------------------

def _clear_all(log):
    for qq in log.quests:
        qq.done = True


def test_streak_breaks_on_skipped_day(tmp_path):
    from flippergotchi.game.quests import QuestLog
    log = QuestLog(str(tmp_path / "q.json"))
    rng = random.Random(1)

    log.roll("2026-06-10", rng=rng)
    _clear_all(log)
    assert log.claim_daily_bonus("2026-06-10") > 0       # streak -> 1

    log.roll("2026-06-11", rng=rng)
    _clear_all(log)
    assert log.claim_daily_bonus("2026-06-11") > 0       # consecutive -> 2
    assert log.streak == 2

    # skip 06-12 entirely, next play is 06-13 -> the run is broken
    log.roll("2026-06-13", rng=rng)
    assert log.streak == 0
    _clear_all(log)
    assert log.claim_daily_bonus("2026-06-13") > 0
    assert log.streak == 1                               # restarts, not continues


# --- daily scrap economy band (MEDIUM) -------------------------------------

def test_daily_fullclear_scrap_in_band():
    from flippergotchi.game import quests as q
    rng = random.Random(12345)
    n, total = 30000, 0
    for _ in range(n):
        picks = q._weighted_distinct(q._TEMPLATES, 3, rng)
        total += sum(p[4].get("scrap", 0) for p in picks) + q.DAILY_CLEAR_BONUS
    mean = total / n
    assert 130 <= mean <= 160, f"daily full-clear scrap mean drifted to {mean:.1f}"


# --- duel-farm guard (MEDIUM) ----------------------------------------------

def test_duel_refuses_depleted_peer(tmp_path, capsys):
    from flippergotchi import commands, prefs
    cfg = _cfg(tmp_path)
    prefs.save(cfg.peers_path, {"P1": {"name": "Broke", "addr": "P1",
                                       "level": 3, "handshakes": 0}})
    commands.cmd_duel(cfg, "Broke")
    out = capsys.readouterr().out
    assert "no handshakes left" in out


def test_duel_win_drains_peer_pool(tmp_path, monkeypatch):
    from flippergotchi import commands, prefs
    from flippergotchi.game import duel as duel_mod
    cfg = _cfg(tmp_path)
    prefs.save(cfg.peers_path, {"P1": {"name": "Rival", "addr": "P1",
                                       "level": 3, "handshakes": 30,
                                       "gear_power": 0, "element": "Aether"}})

    forced = duel_mod.DuelResult(winner="me", loser="Rival", you_won=True,
                                 stake=5, your_power=1.0, their_power=1.0,
                                 your_roll=1.0, their_roll=0.0, log=["win"])
    monkeypatch.setattr(commands.duel_mod, "duel", lambda *a, **k: forced)

    commands.cmd_duel(cfg, "Rival")
    after = prefs.load(cfg.peers_path)["P1"]["handshakes"]
    assert after == 25                                   # 30 - stake(5), persisted

    # the opponent sprite the render used must be a real, non-fallback sprite
    import os
    from flippergotchi.view import battle_screen
    from flippergotchi.view import screens
    name = screens.opponent_sprite("P1")
    assert os.path.exists(os.path.join(battle_screen._SPRITES, name + ".png"))


# --- TrackerLog safety hardening (MEDIUM) ----------------------------------

def test_is_stalker_survives_partial_entry(tmp_path):
    from flippergotchi.game.ble import TrackerLog
    cfg = Config()
    tl = TrackerLog(str(tmp_path / "t.json"))
    tl._seen["x"] = {"count": 9}                         # missing first/last
    assert tl.is_stalker("x", cfg) is False              # no KeyError


def test_tracker_alert_fires_within_window(tmp_path):
    from flippergotchi.game.ble import TrackerLog
    cfg = Config()
    tl = TrackerLog(str(tmp_path / "t.json"))
    for i in range(5):
        tl.record("dev", "AirTag", now=1000.0 + i * 40.0)   # spans 160s > window
    assert tl.should_alert("dev", cfg) is True
    assert tl.should_alert("dev", cfg) is False          # fires exactly once


# --- flipctl HP/damage thresholds (LOW) ------------------------------------

@pytest.mark.parametrize("hp,tier", [(100, 0), (67, 0), (66, 1), (41, 1),
                                     (40, 2), (19, 2), (18, 3), (0, 3)])
def test_dmg_level_thresholds(hp, tier):
    from flippergotchi.view import flipctl
    assert flipctl._dmg_level(hp) == tier


@pytest.mark.parametrize("pct,col", [(100, "#58d858"), (51, "#58d858"),
                                     (50, "#f0c020"), (21, "#f0c020"),
                                     (20, "#e85040"), (0, "#e85040")])
def test_hp_color_thresholds(pct, col):
    from flippergotchi.view import flipctl
    assert flipctl._hp_color(pct) == col
