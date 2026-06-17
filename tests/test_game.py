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
    p = assess({"ssid": "x", "encryption": "wpa"}).difficulty
    w = assess({"ssid": "x", "encryption": "wpa2"}).difficulty
    assert o < p < w


def test_default_ssid_lowers_difficulty():
    base = assess({"ssid": "Randomname", "encryption": "wpa2"}).difficulty
    netg = assess({"ssid": "NETGEAR42", "encryption": "wpa2"}).difficulty
    assert netg < base


def test_monster_from_ap_marks_capture():
    m = monsters.from_ap({"ssid": "Home", "bssid": "AA:BB:CC:DD:EE:FF",
                          "encryption": "wpa2", "kind": "handshake", "band": "5GHz"})
    assert m.kind == "wifi" and m.captured and m.defense > 0


def test_battle_no_longer_refuses_on_scope():
    # authorization is the on-screen consent warning, not a network allow-list,
    # so battle() itself never returns "refused" (it cracks / fails / etc.)
    cfg = Config(simulate=True)
    m = monsters.from_ap({"ssid": "Stranger", "bssid": "11:22:33:44:55:66",
                          "encryption": "wpa2", "kind": "handshake"})
    assert battle.battle(m, cfg)["result"] != "refused"


def test_only_crackable_encryptions_spawn():
    # the sim never surfaces WPA3/Enterprise APs
    from flippergotchi.core.bettercap import _rand_ap, CRACKABLE
    assert all(_rand_ap()["encryption"] in CRACKABLE for _ in range(100))


def test_battle_cracks_weak_when_authorized():
    cfg = Config(simulate=True)
    cfg.home_networks = ["Mine"]
    m = monsters.from_ap({"ssid": "Mine", "bssid": "AA:11:22:33:44:55",
                          "encryption": "open", "kind": "handshake"})
    random.seed(1)
    r = battle.battle(m, cfg, force_authorized=True)
    assert r["result"] == "cracked" and m.defeated and m.key


def test_ble_battle_cracks_pairing():
    cfg = Config(simulate=True)
    random.seed(1)
    # audio device -> Just Works pairing -> crackable
    m = monsters.from_ble({"addr": "AA:BB:CC:DD:EE:01", "name": "Buds",
                           "device_class": "audio", "rssi": -60})
    r = battle.battle(m, cfg)
    assert r["result"] == "cracked" and m.defeated and m.key


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all good")
