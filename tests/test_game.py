"""Monster / analyst / battle checks."""
from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flippergotchi.config import Config
from flippergotchi.game import battle, monsters
from flippergotchi.game.analysis import assess


def test_difficulty_orders_by_encryption():
    o = assess({"ssid": "x", "encryption": "open"}).difficulty
    w = assess({"ssid": "x", "encryption": "wpa2"}).difficulty
    t = assess({"ssid": "x", "encryption": "wpa3"}).difficulty
    assert o < w < t


def test_default_ssid_lowers_difficulty():
    base = assess({"ssid": "Randomname", "encryption": "wpa2"}).difficulty
    netg = assess({"ssid": "NETGEAR42", "encryption": "wpa2"}).difficulty
    assert netg < base


def test_monster_from_ap_marks_capture():
    m = monsters.from_ap({"ssid": "Home", "bssid": "AA:BB:CC:DD:EE:FF",
                          "encryption": "wpa2", "kind": "handshake", "band": "5GHz"})
    assert m.kind == "wifi" and m.captured and m.defense > 0


def test_battle_refused_without_authorization():
    cfg = Config()  # empty home_networks
    m = monsters.from_ap({"ssid": "Stranger", "bssid": "11:22:33:44:55:66",
                          "encryption": "wpa2", "kind": "handshake"})
    assert battle.battle(m, cfg)["result"] == "refused"


def test_battle_wpa3_is_immune():
    cfg = Config()
    cfg.home_networks = ["Mine"]
    m = monsters.from_ap({"ssid": "Mine", "bssid": "11:22:33:44:55:66",
                          "encryption": "wpa3", "kind": "handshake"})
    assert battle.battle(m, cfg, force_authorized=True)["result"] == "immune"


def test_battle_cracks_weak_when_authorized():
    cfg = Config(simulate=True)
    cfg.home_networks = ["Mine"]
    m = monsters.from_ap({"ssid": "Mine", "bssid": "AA:11:22:33:44:55",
                          "encryption": "open", "kind": "handshake"})
    random.seed(1)
    r = battle.battle(m, cfg, force_authorized=True)
    assert r["result"] == "cracked" and m.defeated and m.key


def test_ble_is_tamed_not_cracked():
    cfg = Config()
    m = monsters.from_ble({"addr": "AA:BB:CC:DD:EE:01", "name": "Buds",
                           "appearance": "audio", "rssi": -60})
    r = battle.battle(m, cfg)
    assert r["result"] == "tamed" and m.defeated


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all good")
