"""BLE battling: pairing crack (crackle) + GATT-write control, difficulty by
pairing security."""
from __future__ import annotations

from flippergotchi.config import Config
from flippergotchi.game import monsters
from flippergotchi.game import blebattle


def _ble(cls, addr="AA:BB:CC:00:11:22", connectable=True):
    return monsters.from_ble({"addr": addr, "name": cls, "device_class": cls,
                              "connectable": connectable, "rssi": -55})


# -- pairing security = defense --------------------------------------------
def test_pairing_security_by_class():
    assert _ble("tracker").pairing == "just_works"     # trivial -> legendary-easy
    assert _ble("wearable").pairing == "pin"
    assert _ble("phone").pairing == "secure"           # LE Secure Connections
    # secure pairing = a much tougher defense than just_works
    assert _ble("phone").defense > _ble("tracker").defense


# -- crack the pairing ------------------------------------------------------
def test_just_works_cracks(monkeypatch):
    monkeypatch.setattr(blebattle.random, "random", lambda: 0.0)
    cfg = Config(simulate=True)
    m = _ble("tracker")
    r = blebattle.battle_ble(m, cfg)
    assert r["result"] == "cracked" and m.defeated and m.key
    assert "ltk" in r["note"].lower() or m.key


def test_secure_non_connectable_is_immune():
    cfg = Config(simulate=True)
    m = _ble("phone", connectable=False)               # secure + can't connect
    r = blebattle.battle_ble(m, cfg)
    assert r["result"] == "immune" and not m.defeated


def test_secure_connectable_falls_back_to_control(monkeypatch):
    monkeypatch.setattr(blebattle.random, "random", lambda: 0.0)  # control lands
    cfg = Config(simulate=True)
    m = _ble("phone", connectable=True)                # secure but connectable
    r = blebattle.battle_ble(m, cfg)
    assert r["result"] == "cracked" and r["via"] == "gatt-write"
    assert m.defeated and "control" in r["note"]


# -- crackle + control helpers ---------------------------------------------
def test_parse_ltk():
    assert blebattle._parse_ltk("LTK: 0011223344556677\n") == "0011223344556677"
    assert blebattle._parse_ltk("nothing here") == ""


def test_control_move_per_species():
    tracker = monsters.from_ble({"addr": "AA:BB:CC:00:00:01",
                                 "device_class": "tracker"})  # -> Trackling
    label, uuid, _ = blebattle.control_move(tracker)
    assert "ring" in label.lower() and uuid                # trackers -> ring it


# -- BLE battle render ------------------------------------------------------
def test_blebattle_render(tmp_path):
    from flippergotchi.view import blebattle_screen
    out = blebattle_screen.render(str(tmp_path / "b.html"),
        {"species": "Trackling", "name": "AirTag", "level": 5, "pairing": "just_works"},
        {"result": "cracked", "via": "crackle", "note": "LTK recovered"})
    html = open(out).read()
    assert "OWNED" in html and "JUST WORKS" in html and "grayscale(1)" in html
    # immune outcome
    out2 = blebattle_screen.render(str(tmp_path / "b2.html"),
        {"species": "Pocketling", "name": "iPhone", "pairing": "secure"},
        {"result": "immune", "via": "-", "note": "LE Secure"})
    assert "IMMUNE" in open(out2).read()
