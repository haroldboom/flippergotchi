"""The Python-3.10 TOML-lite fallback parser + the authorization gate."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flippergotchi.config import _parse_toml_lite
from flippergotchi.config import Config
from flippergotchi.game import battle, monsters


def test_parses_types():
    d = _parse_toml_lite('name = "Flippy"\ncloud_enabled = true\nradius = 80.0\nn = 5')
    assert d["name"] == "Flippy"
    assert d["cloud_enabled"] is True
    assert d["radius"] == 80.0 and d["n"] == 5


def test_array_with_inline_comment_stays_a_list():
    # the bug that wrongly bypassed the gate: a trailing comment broke the array
    d = _parse_toml_lite('home_networks = ["HomeNet", "Linksys"]   # my own gear')
    assert d["home_networks"] == ["HomeNet", "Linksys"]


def test_quoted_hash_is_not_a_comment():
    d = _parse_toml_lite('ssid = "net#1"')
    assert d["ssid"] == "net#1"


def _mon(ssid):
    return monsters.from_ap({"ssid": ssid, "bssid": "AA:BB:CC:DD:EE:01",
                             "encryption": "wpa2", "kind": "handshake"})


def test_gate_allows_only_home_networks():
    cfg = Config()
    cfg.home_networks = ["HomeNet", "Linksys"]
    assert battle.is_authorized(_mon("HomeNet_5G"), cfg) is True
    assert battle.is_authorized(_mon("OPTUS_A1B2"), cfg) is False


def test_gate_survives_a_string_home_networks():
    # even if misconfigured as a bare string, we must NOT iterate its characters
    cfg = Config()
    cfg.home_networks = "HomeNet"
    assert battle.is_authorized(_mon("OPTUS_A1B2"), cfg) is False
    assert battle.is_authorized(_mon("HomeNet"), cfg) is True


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all good")
