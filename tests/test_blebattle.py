"""Befriending BLE signal-sprites: multi-step courtship sequence, the bashful
"ease its guard" path, class-specific keepsake loot, temperament (pairing
security) difficulty, and the frame render."""
from __future__ import annotations

from flippergotchi.config import Config
from flippergotchi.game import monsters
from flippergotchi.game import blebattle


def _ble(cls, addr="AA:BB:CC:00:11:22", connectable=True):
    return monsters.from_ble({"addr": addr, "name": cls, "device_class": cls,
                              "connectable": connectable, "rssi": -55})


def _roll(monkeypatch, value):
    monkeypatch.setattr(blebattle.random, "random", lambda: value)


# -- pairing security = defense --------------------------------------------
def test_pairing_security_by_class():
    assert _ble("tracker").pairing == "just_works"
    assert _ble("wearable").pairing == "pin"
    assert _ble("phone").pairing == "secure"
    assert _ble("phone").defense > _ble("tracker").defense


# -- the technique sequence + outcomes -------------------------------------
def test_just_works_cracks_with_steps_and_loot(monkeypatch):
    _roll(monkeypatch, 0.0)                    # befriend lands
    m = _ble("tracker")
    r = blebattle.battle_ble(m, Config(simulate=True))
    assert r["result"] == "cracked" and m.defeated and m.key
    labels = [s[0] for s in r["steps"]]
    assert "LISTEN" in labels and "HUM" in labels and "FRIEND" in labels
    assert r["loot"] == "a wandering spark"    # tracker keepsake


def test_pin_forces_a_greet_step(monkeypatch):
    _roll(monkeypatch, 0.0)
    r = blebattle.battle_ble(_ble("wearable"), Config(simulate=True))
    assert "GREET" in [s[0] for s in r["steps"]]


def test_secure_bashful_when_ease_fails_and_not_connectable(monkeypatch):
    _roll(monkeypatch, 0.9)                    # can't ease its guard
    m = _ble("phone", connectable=False)
    r = blebattle.battle_ble(m, Config(simulate=True))
    assert r["result"] == "immune" and not m.defeated
    assert "BASHFUL" in [s[0] for s in r["steps"]]


def test_secure_ease_guard_befriends(monkeypatch):
    _roll(monkeypatch, 0.0)                    # ease lands -> befriend
    m = _ble("phone", connectable=False)
    r = blebattle.battle_ble(m, Config(simulate=True))
    assert r["result"] == "cracked" and m.defeated
    assert "EASE" in [s[0] for s in r["steps"]]
    assert "knob" in r["via"]


def test_secure_connectable_boop_when_ease_fails(monkeypatch):
    _roll(monkeypatch, 0.5)                    # ease fails (0.5>=0.35), boop lands (0.5<0.7)
    m = _ble("phone", connectable=True)        # bashful, but connectable
    r = blebattle.battle_ble(m, Config(simulate=True))
    assert r["result"] == "cracked" and r["via"] == "gatt-write"
    assert "BOOP" in [s[0] for s in r["steps"]]


# -- helpers ----------------------------------------------------------------
def test_parse_ltk():
    assert blebattle._parse_ltk("LTK: 0011223344556677\n") == "0011223344556677"
    assert blebattle._parse_ltk("nothing here") == ""


def test_control_move_per_species():
    tracker = monsters.from_ble({"addr": "AA:BB:CC:00:00:01",
                                 "device_class": "tracker"})
    label, uuid, _ = blebattle.control_move(tracker)
    assert "jingle" in label.lower() and uuid


def test_loot_per_species():
    from flippergotchi.game.blebattle import _LOOT
    assert _LOOT["Echobub"] == "a looping echo"
    assert _LOOT["Vitalix"] == "a steady pulse-mote"


# -- render -----------------------------------------------------------------
def test_render_sequence(tmp_path, monkeypatch):
    _roll(monkeypatch, 0.0)
    m = _ble("tracker")
    res = blebattle.battle_ble(m, Config(simulate=True))
    from flippergotchi.view import blebattle_screen
    paths = blebattle_screen.render_sequence(
        str(tmp_path), {"species": "Trackling", "name": "AirTag",
                        "pairing": "just_works"}, res)
    assert len(paths) == len(res["steps"])
    last = open(paths[-1]).read()
    assert "FRIEND" in last and "OPEN" in last and "grayscale(1)" in last
    assert "SIGNAL SPRITE" in last
