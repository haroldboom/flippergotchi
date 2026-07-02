"""Ledger, BSSID-dedup, hidden labels, and warning-prefs checks."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flippergotchi import prefs as prefs_mod
from flippergotchi.game import monsters
from flippergotchi.game.bestiary import Bestiary
from flippergotchi.game.ledger import Ledger


def _ap(bssid, ssid="Net", **kw):
    ev = {"ssid": ssid, "bssid": bssid, "encryption": "wpa2",
          "band": "2.4GHz", "clients": 0, "signal": -60}
    ev.update(kw)
    return monsters.from_ap(ev)


def test_ledger_counts_categories(tmp_file):
    led = Ledger(tmp_file("l.json"))
    m = _ap("AA:BB:CC:DD:EE:01")
    assert led.record(m, "cracked", "local", "pw") == "win"
    assert led.record(m, "failed") == "loss"
    assert led.record(m, "submitted", "wpa-sec") == "escalate"
    assert led.record(m, "refused") is None        # not a real attempt
    assert led.record(m, "immune") is None
    c = led.counts()
    assert (c["win"], c["loss"], c["escalate"]) == (1, 1, 1)


def test_ledger_persists(tmp_file):
    p = tmp_file("l.json")
    led = Ledger(p)
    led.record(_ap("AA:BB:CC:DD:EE:02"), "cracked")
    led.record(_ap("AA:BB:CC:DD:EE:03"), "failed")
    led.save()
    reloaded = Ledger(p).counts()
    assert reloaded["win"] == 1 and reloaded["loss"] == 1


def test_bestiary_dedupes_by_bssid_not_ssid(tmp_file):
    dex = Bestiary(tmp_file("b.json"))
    # two DIFFERENT hidden networks (blank ssid) with distinct BSSIDs
    assert dex.add(_ap("AA:BB:CC:00:00:01", ssid="")) is True
    assert dex.add(_ap("AA:BB:CC:00:00:02", ssid="")) is True
    # same BSSID seen again = not new
    assert dex.add(_ap("AA:BB:CC:00:00:01", ssid="")) is False
    assert len(dex.all()) == 2


def test_bestiary_rejects_placeholder_bssid(tmp_file):
    dex = Bestiary(tmp_file("b.json"))
    assert dex.add(_ap("00:00:00:00:00:00")) is False
    assert len(dex.all()) == 0


def test_hidden_label_is_unique_per_bssid():
    a = monsters.label(_ap("AA:BB:CC:00:00:01", ssid=""))
    b = monsters.label(_ap("AA:BB:CC:00:00:02", ssid=""))
    assert a != b and "hidden" in a


def test_prefs_roundtrip(tmp_file):
    p = tmp_file("p.json")
    assert prefs_mod.load(p) == {}
    prefs_mod.save(p, {"hide_battle_warning": True})
    assert prefs_mod.load(p)["hide_battle_warning"] is True


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all good")
