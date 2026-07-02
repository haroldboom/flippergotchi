"""The shiny mechanic: stable ~1/256 shiny roll per AP/device, bestiary merge,
build_stats sourcing, and the (now reachable) shiny_find achievement."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flippergotchi.game import achievements as ach
from flippergotchi.game import monsters
from flippergotchi.game.bestiary import Bestiary
from flippergotchi.pet.state import PetState

# A BSSID / BLE addr that hash to shiny under the stable roll (see monsters._is_shiny).
SHINY_BSSID = "AA:BB:CC:00:00:42"
SHINY_BLE_ADDR = "DD:EE:FF:00:00:75"
PLAIN_BSSID = "AA:BB:CC:11:22:33"


def _ap(bssid, ssid="SomeNet", enc="wpa2"):
    return {"type": "ap", "ssid": ssid, "bssid": bssid, "encryption": enc,
            "band": "2.4GHz", "clients": 1, "signal": -55, "kind": "handshake"}


def _ble(addr, cls="audio"):
    return {"addr": addr, "name": "Buds", "device_class": cls, "rssi": -60,
            "company": "Apple"}


# -- the roll itself --------------------------------------------------------
def test_default_monster_not_shiny():
    m = monsters.from_ap(_ap(PLAIN_BSSID))
    assert m.shiny is False


def test_forced_shiny_ap_sets_flag():
    m = monsters.from_ap(_ap(SHINY_BSSID))
    assert m.shiny is True


def test_forced_shiny_ble_sets_flag():
    m = monsters.from_ble(_ble(SHINY_BLE_ADDR))
    assert m.shiny is True


def test_shiny_is_stable_for_same_id():
    # the same id is shiny every time (never time-based); a different id isn't.
    first = monsters.from_ap(_ap(SHINY_BSSID)).shiny
    second = monsters.from_ap(_ap(SHINY_BSSID, ssid="Renamed", enc="open")).shiny
    assert first is second is True
    assert monsters._is_shiny(SHINY_BSSID) is True
    assert monsters._is_shiny(PLAIN_BSSID) is False


def test_shiny_roll_is_rare():
    # roughly 1/256: a few thousand distinct ids should yield only a handful.
    ids = ["AA:BB:CC:%02X:%02X:%02X" % ((i >> 16) & 255, (i >> 8) & 255, i & 255)
           for i in range(4096)]
    shinies = sum(1 for b in ids if monsters._is_shiny(b))
    assert 1 <= shinies <= 60  # ~16 expected, generous bounds


# -- bestiary merge ---------------------------------------------------------
def test_bestiary_preserves_shiny_on_merge(tmp_file):
    dex = Bestiary(tmp_file("dex.json"))
    m = monsters.from_ap(_ap(SHINY_BSSID))
    assert dex.add(m) is True
    # a later sighting of the same AP (re-add) must not clear the shiny flag
    dex.add(monsters.from_ap(_ap(SHINY_BSSID)))
    assert dex.get(SHINY_BSSID).shiny is True


# -- build_stats sourcing ---------------------------------------------------
def test_build_stats_counts_captured_shinies(tmp_file):
    dex = Bestiary(tmp_file("dex.json"))
    shiny = monsters.from_ap(_ap(SHINY_BSSID))      # captured (handshake) + shiny
    plain = monsters.from_ap(_ap(PLAIN_BSSID))      # captured, not shiny
    dex.add(shiny)
    dex.add(plain)
    stats = ach.build_stats(PetState(), dex=dex)
    assert stats["shinies"] == 1


def test_build_stats_ignores_uncaptured_shiny(tmp_file):
    dex = Bestiary(tmp_file("dex.json"))
    m = monsters.from_ap(_ap(SHINY_BSSID))
    m.captured = False                              # only spotted, not captured
    dex.add(m)
    assert ach.build_stats(PetState(), dex=dex)["shinies"] == 0


def test_build_stats_handles_dex_none():
    # signature must still work for callers passing dex=None
    assert ach.build_stats(PetState(), dex=None)["shinies"] == 0


# -- achievement unlock -----------------------------------------------------
def test_shiny_find_is_no_longer_hidden():
    assert ach.get("shiny_find").hidden is False


def test_shiny_find_unlocks_when_shinies_at_least_one(tmp_file):
    book = ach.AchievementBook(tmp_file("a.json"))
    assert book.check({"shinies": 0}) == []
    newly = book.check({"shinies": 1})
    assert any(b.id == "shiny_find" for b in newly)
    assert book.is_unlocked("shiny_find")


# -- display surfacing ------------------------------------------------------
def test_species_label_tags_shiny():
    m = monsters.from_ap(_ap(SHINY_BSSID))
    assert "SHINY" in monsters.species_label(m)
    plain = monsters.from_ap(_ap(PLAIN_BSSID))
    assert monsters.species_label(plain) == plain.species
