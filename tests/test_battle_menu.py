"""The home Battle Dojo: menu + scrollable target list render, and the
'fresh targets' pool that AUTO/MANUAL battle draws from."""
from __future__ import annotations

import dataclasses

from flippergotchi.config import Config
from flippergotchi import commands
from flippergotchi.view import battle_menu
from flippergotchi.game.bestiary import Bestiary
from flippergotchi.game import monsters


def _ap(ssid, enc="wpa2", bssid="AA:BB:CC:00:00:01"):
    return monsters.from_ap({"type": "ap", "ssid": ssid, "bssid": bssid,
                             "encryption": enc, "band": "2.4GHz",
                             "clients": 1, "signal": -55})


def test_menu_render(tmp_path):
    out = battle_menu.render_menu(str(tmp_path / "m.html"), ready=4, cracked=2)
    html = open(out).read()
    assert "BATTLE DOJO" in html and "AUTO BATTLE" in html and "MANUAL" in html
    assert "4 ready" in html and "2 cracked" in html
    assert "OK" in html and "Back" in html        # button hints


def test_list_render_with_cursor_and_tags(tmp_path):
    items = [{"name": "NETGEAR", "level": 9, "encryption": "wpa2"},
             {"name": "OldAP", "level": 1, "encryption": "wep", "rarity": "legendary"}]
    out = battle_menu.render_list(str(tmp_path / "l.html"), items, cursor=1)
    html = open(out).read()
    assert "NETGEAR" in html and "OldAP" in html
    assert "LEGENDARY" in html and "WPA2" in html
    assert "1/2" in html or "2/2" in html          # position indicator


def test_list_empty(tmp_path):
    out = battle_menu.render_list(str(tmp_path / "l.html"), [])
    assert "No captured targets" in open(out).read()


def test_button_map_is_defined():
    b = battle_menu.BUTTONS
    assert b["up"] and b["down"] and b["select"] and b["back"] and b["open"]


def test_ready_targets_only_fresh_captured_wifi(tmp_path):
    cfg = Config()
    for f in dataclasses.fields(cfg):
        v = getattr(cfg, f.name)
        if isinstance(v, str) and v.startswith("~/.flippergotchi"):
            setattr(cfg, f.name, str(tmp_path / f.name))
    dex = Bestiary(cfg.bestiary_path)
    fresh = _ap("NETGEAR", bssid="AA:BB:CC:00:00:01"); fresh.captured = True
    battled = _ap("Linksys", bssid="AA:BB:CC:00:00:02"); battled.captured = True
    battled.attempts = 1                       # already battled -> excluded
    done = _ap("HomeNet", bssid="AA:BB:CC:00:00:03"); done.captured = True
    done.defeated = True                       # already cracked -> excluded
    uncaught = _ap("Cafe", bssid="AA:BB:CC:00:00:04")  # not captured -> excluded
    for m in (fresh, battled, done, uncaught):
        dex.add(m)
    ready = commands._ready_targets(dex)
    ids = {m.id for m in ready}
    assert ids == {"AA:BB:CC:00:00:01"}
