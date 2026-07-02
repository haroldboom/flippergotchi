"""The agent runs a REAL capture on a live backend (native/bettercap) and lets
the radio decide the outcome; in sim it never touches the backend's capture.
Hermetic: a fake backend + a hand-built pcap fixture, no radio."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import test_handshake as T  # tiny binary pcap fixture builders

from flippergotchi.agent import Agent
from flippergotchi.pet.state import PetState

_EV = {"type": "ap", "bssid": "AA:BB:CC:00:11:22", "ssid": "Home",
       "encryption": "wpa2", "band": "2.4GHz", "clients": 2, "signal": -50}


class _FakeBackend:
    def __init__(self, name, path):
        self.name = name
        self._path = path
        self.calls = 0

    def start(self):
        pass

    def scan(self):
        return []

    def capture_handshake(self, bssid, ssid="", timeout=25):
        self.calls += 1
        return self._path

    def stop(self):
        pass


def test_live_capture_validates_and_keeps_path(make_cfg, tmp_path):
    cap = tmp_path / "hs.pcap"
    T._write(str(cap), [T._m1(), T._m2(), T._m3()])     # a usable 4-way
    a = Agent(make_cfg(), PetState(name="T"))
    a.wifi = _FakeBackend("bettercap", str(cap))
    captured, path = a._live_capture(_EV)
    assert captured is True and path == str(cap)


def test_live_capture_none_is_escape(make_cfg):
    a = Agent(make_cfg(), PetState(name="T"))
    a.wifi = _FakeBackend("native", None)
    assert a._live_capture(_EV) == (False, "")


def test_live_capture_incomplete_capture_is_escape(make_cfg, tmp_path):
    cap = tmp_path / "junk.pcap"
    T._write(str(cap), [T._m1()])                       # only M1 -> not usable
    a = Agent(make_cfg(), PetState(name="T"))
    a.wifi = _FakeBackend("native", str(cap))
    captured, path = a._live_capture(_EV)
    assert captured is False and path == ""


def test_encounter_uses_live_backend_and_stores_path(make_cfg, tmp_path, monkeypatch):
    cap = tmp_path / "hs.pcap"
    T._write(str(cap), [T._m1(), T._m2(), T._m3()])
    a = Agent(make_cfg(), PetState(name="T"))
    a.wifi = _FakeBackend("bettercap", str(cap))
    monkeypatch.setattr(a, "_choose", lambda m: "capture")
    a._encounter(_EV)
    m = a.dex.get("AA:BB:CC:00:11:22")
    assert m is not None and m.captured and m.capture_path == str(cap)
    assert a.wifi.calls == 1                            # the real capture ran


def test_sim_backend_never_calls_real_capture(make_cfg, monkeypatch):
    a = Agent(make_cfg(), PetState(name="T"))
    assert getattr(a.wifi, "name", "") == "sim"          # default in --simulate
    called = {"n": 0}

    def spy(*x, **k):
        called["n"] += 1
        return None

    monkeypatch.setattr(a.wifi, "capture_handshake", spy)
    monkeypatch.setattr(a, "_choose", lambda m: "capture")
    a._encounter(_EV)
    assert called["n"] == 0                              # sim stays synthetic
