"""The render/output seam (P1 item 6): every screen renderer is now split into a
PURE ``..._html(...)`` builder and a thin public entry point that routes the write
through ``view/sink.py``.

These tests pin the seam down:
  * ``view.sink`` performs the file I/O (creates dirs, writes bytes, expands ~);
  * for each refactored screen the pure ``..._html()`` returns EXACTLY the string
    the public ``render*`` writes to disk (golden: the file content equals the
    pure output), and the public entry point still returns/writes as before.
"""
from __future__ import annotations

import os

from flippergotchi.config import Config
from flippergotchi.pet.state import PetState
from flippergotchi.game import achievements as ach_mod
from flippergotchi.game.equipment import Inventory
from flippergotchi.game.larder import Larder
from flippergotchi.view import sink
from flippergotchi.view import (
    flipctl, encounter_screen, battle_screen, equip_screen, feed_screen,
    badge_screen, battle_menu, capture_screen, blebattle_screen,
)


class _State:
    name = "Sharkey"
    active_title = ""
    titles: list = []


# --- the sink itself -------------------------------------------------------

def test_sink_write_creates_dirs_and_writes(tmp_path):
    p = tmp_path / "deep" / "nested" / "out.html"
    ret = sink.write(str(p), "<html>hi</html>")
    assert ret == str(p)
    assert os.path.isdir(str(tmp_path / "deep" / "nested"))
    assert open(str(p)).read() == "<html>hi</html>"


def test_sink_filesink_matches_module_write(tmp_path):
    a = tmp_path / "a.html"
    b = tmp_path / "b.html"
    r1 = sink.FileSink().write(str(a), "<x>")
    r2 = sink.write(str(b), "<x>")
    assert open(r1).read() == open(r2).read() == "<x>"


def test_sink_expands_user(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    ret = sink.write("~/flip_out.html", "<y>")
    assert ret == str(tmp_path / "flip_out.html")
    assert open(ret).read() == "<y>"


def test_sink_returns_no_dir_path(tmp_path, monkeypatch):
    # a bare filename (no dirname) must not blow up on makedirs
    monkeypatch.chdir(tmp_path)
    ret = sink.write("bare.html", "<z>")
    assert open(ret).read() == "<z>"


# --- flipctl ----------------------------------------------------------------

def test_flipctl_pure_matches_written(tmp_path):
    state = PetState(name="Flippy")
    cfg = Config()
    cfg.flipctl_html_out = str(tmp_path / "face.html")
    expected = flipctl.render_html(state, cfg)
    out = flipctl.render(state, cfg)
    assert out == cfg.flipctl_html_out
    assert open(out).read() == expected


# --- encounter_screen -------------------------------------------------------

_MON = {"species": "Crypterion", "name": "OPTUS_A1B2", "level": 11,
        "encryption": "wpa2", "defense": 72, "kind": "wifi"}


def test_encounter_pure_matches_written(tmp_path):
    expected = encounter_screen.render_html(_MON, "hi!")
    out = encounter_screen.render(str(tmp_path / "enc.html"), _MON, "hi!")
    assert out == str(tmp_path / "enc.html")
    assert open(out).read() == expected


# --- battle_screen ----------------------------------------------------------

def test_battle_pure_matches_written(tmp_path):
    you = {"name": "Me", "level": 5, "sprite": "adult", "health": 80}
    them = {"name": "You", "level": 6, "sprite": "adult", "health": 40}
    expected = battle_screen.render_html(you, them, "clash!")
    out = battle_screen.render(str(tmp_path / "b.html"), you, them, "clash!")
    assert open(out).read() == expected


# --- equip_screen -----------------------------------------------------------

def test_equip_pure_matches_written(tmp_path):
    inv = Inventory(str(tmp_path / "inv.json"))
    expected = equip_screen.render_html(inv, "adult")
    out = equip_screen.render(str(tmp_path / "eq.html"), inv, "adult")
    assert open(out).read() == expected


# --- feed_screen ------------------------------------------------------------

def test_feed_pure_matches_written(tmp_path):
    state = PetState(name="Flippy")
    cfg = Config()
    larder = Larder(str(tmp_path / "l.json"), capacity=10)
    larder.add("chum", 2)
    expected = feed_screen.render_html(state, cfg, larder)
    out = feed_screen.render(str(tmp_path / "feed.html"), state, cfg, larder)
    assert open(out).read() == expected


# --- badge_screen -----------------------------------------------------------

def test_badge_pure_matches_written(tmp_path):
    book = ach_mod.AchievementBook(str(tmp_path / "ach.json"))
    book._unlocked.add("first_catch")
    stats = {"catches": 1, "cracks": 0, "duel_wins": 0, "distance_m": 0,
             "level": 1, "stage": "egg", "equipped_slots": 0, "shinies": 0,
             "quests_done": 0, "streak": 0}
    expected = badge_screen.render_html(book, stats, _State())
    out = badge_screen.render(str(tmp_path / "badges.html"), book, stats, _State())
    assert open(out).read() == expected


# --- battle_menu ------------------------------------------------------------

def test_battle_menu_pure_matches_written(tmp_path):
    expected = battle_menu.menu_html(ready=4, cracked=2)
    out = battle_menu.render_menu(str(tmp_path / "m.html"), ready=4, cracked=2)
    assert open(out).read() == expected


def test_battle_list_pure_matches_written(tmp_path):
    items = [{"name": "NETGEAR", "level": 9, "encryption": "wpa2"},
             {"name": "OldAP", "level": 1, "encryption": "wep",
              "rarity": "legendary"}]
    expected = battle_menu.list_html(items, cursor=1)
    out = battle_menu.render_list(str(tmp_path / "l.html"), items, cursor=1)
    assert open(out).read() == expected


def test_battle_list_empty_pure_matches_written(tmp_path):
    expected = battle_menu.list_html([])
    out = battle_menu.render_list(str(tmp_path / "l.html"), [])
    assert open(out).read() == expected


# --- capture_screen (multi-frame) ------------------------------------------

def test_capture_sequence_pure_matches_written(tmp_path):
    mon = {"species": "Crypterion", "name": "OPTUS_A1B2"}
    expected = capture_screen.sequence_html(mon, caught=True, deauth=5, timeout=20)
    paths = capture_screen.render_sequence(str(tmp_path), mon, caught=True,
                                           deauth=5, timeout=20)
    assert len(paths) == len(expected) == 4
    for p, html in zip(paths, expected):
        assert p == os.path.join(str(tmp_path), os.path.basename(p))
        assert open(p).read() == html


# --- blebattle_screen (multi-frame) ----------------------------------------

def test_blebattle_sequence_pure_matches_written(tmp_path):
    mon = {"species": "Trackling", "name": "AirTag", "pairing": "just_works"}
    result = {"steps": [("SNIFF", "listening"), ("OWNED", "pwned")]}
    expected = blebattle_screen.sequence_html(mon, result)
    paths = blebattle_screen.render_sequence(str(tmp_path), mon, result)
    assert len(paths) == len(expected) == 2
    for p, html in zip(paths, expected):
        assert open(p).read() == html
