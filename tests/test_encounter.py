"""Encounter state machine + home-gate checks."""
from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flippergotchi.config import Config
from flippergotchi.game import encounter, monsters
from flippergotchi.game.home import at_home


def _mon(**kw):
    ev = {"ssid": "Net", "bssid": "AA:BB:CC:DD:EE:FF", "encryption": "wpa2",
          "band": "2.4GHz", "clients": 0, "signal": -60}
    ev.update(kw)
    return monsters.from_ap(ev)


class _AlwaysHit:
    @staticmethod
    def random():
        return 0.0  # below any capture_chance -> always catch


class _AlwaysMiss:
    @staticmethod
    def random():
        return 1.0  # above any capture_chance -> never catch


def test_run_leads_to_fled():
    e = encounter.Encounter(_mon())
    e.choose("run")
    assert e.state == encounter.FLED and e.animation == "flee"


def test_capture_success_marks_caught():
    m = _mon(clients=3, signal=-45)
    e = encounter.Encounter(m)
    e.choose("capture", rng=_AlwaysHit)
    assert e.state == encounter.CAUGHT and m.captured and e.animation == "catch"


def test_capture_failure_escapes():
    m = _mon()
    e = encounter.Encounter(m)
    e.choose("capture", rng=_AlwaysMiss)
    assert e.state == encounter.ESCAPED and not m.captured


def test_resolve_capture_from_real_outcome():
    # hardware path: a real backend captured a usable handshake
    m = _mon()
    e = encounter.Encounter(m)
    e.resolve_capture(True, path="/tmp/hs_aabb.pcapng")
    assert e.state == encounter.CAUGHT and m.captured
    assert m.capture_path == "/tmp/hs_aabb.pcapng"


def test_resolve_capture_no_handshake_escapes():
    m = _mon(clients=4, signal=-40)   # great RF odds, but the radio got nothing
    e = encounter.Encounter(m)
    e.resolve_capture(False)
    assert e.state == encounter.ESCAPED and not m.captured and not m.capture_path


def test_capture_chance_rewards_clients_and_signal():
    weak = encounter.capture_chance(_mon(clients=0, signal=-85))
    strong = encounter.capture_chance(_mon(clients=4, signal=-40))
    assert strong > weak


def test_auto_choice_is_capture_or_run():
    assert encounter.auto_choice(_mon()) in ("capture", "run")


def test_at_home_via_visible_network():
    cfg = Config()
    cfg.home_networks = ["MyHome"]
    assert at_home(cfg, visible_ssids=["Neighbour", "MyHome_5G"]) is True
    assert at_home(cfg, visible_ssids=["Cafe", "Airport"]) is False


def test_at_home_via_geofence():
    cfg = Config()
    cfg.home_location = [-31.95, 115.86]
    cfg.home_radius_m = 100.0
    assert at_home(cfg, lat=-31.9501, lon=115.8601) is True   # ~15 m away
    assert at_home(cfg, lat=-31.96, lon=115.87) is False      # ~1.4 km away


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all good")
