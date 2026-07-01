"""The pure render helpers in ``view/screens.py`` reproduce, exactly, what the
inline ``commands.py`` helpers produce -- but they RETURN their output instead of
printing it. Where practical each test golden-compares against the original
``commands`` helper (still present at this refactor stage)."""
from __future__ import annotations

import io
import types
from contextlib import redirect_stdout

from flippergotchi import commands
from flippergotchi.game import monsters
from flippergotchi.view import screens


def _cfg(tmp_path, **over):
    base = dict(
        character_variant="classic",
        capture_frames_dir=str(tmp_path / "capture"),
        encounter_html_out=str(tmp_path / "encounter.html"),
        capture_timeout=20,
        deauth_count=5,
    )
    base.update(over)
    return types.SimpleNamespace(**base)


def _monster(ssid="DemoNet", bssid="AA:BB:CC:11:22:33"):
    ev = {"type": "ap", "ssid": ssid, "bssid": bssid, "encryption": "wpa2",
          "band": "5GHz", "clients": 3, "signal": -52}
    return monsters.from_ap(ev)


# --- player_stem ----------------------------------------------------------

def test_player_stem_classic_and_variant():
    assert screens.player_stem(types.SimpleNamespace(character_variant="classic")) == "adult"
    assert screens.player_stem(types.SimpleNamespace(character_variant="")) == "adult"
    assert screens.player_stem(types.SimpleNamespace(character_variant="neon")) == "neon-adult"
    # missing attr defaults to classic
    assert screens.player_stem(types.SimpleNamespace()) == "adult"


def test_player_stem_from_cfg(tmp_path):
    for variant in ("classic", "", "neon", "gold"):
        cfg = _cfg(tmp_path, character_variant=variant)
        expected = "adult" if variant in ("classic", "") else f"{variant}-adult"
        assert screens.player_stem(cfg) == expected


# --- opponent_sprite ------------------------------------------------------

def test_opponent_sprite_deterministic():
    _species = ("hammerhead", "goblin", "sawshark", "whaleshark")
    for key in ("AA:BB:CC:DD:EE:FF", "rival", "", None, "x", "peer-2"):
        got = screens.opponent_sprite(key)
        idx = sum(ord(c) for c in (key or "x")) % len(_species)
        assert got == f"{_species[idx]}-adult"
        assert got.endswith("-adult")
    # stable per key
    assert screens.opponent_sprite("rival") == screens.opponent_sprite("rival")


# --- render_encounter -----------------------------------------------------

def test_render_encounter_returns_path(tmp_path):
    m = _monster()
    cfg_a = _cfg(tmp_path / "a")
    out_new = screens.render_encounter(cfg_a, m)
    assert out_new
    html = open(out_new).read()
    assert m.species in html and "WPA2" in html


def test_render_encounter_custom_line(tmp_path):
    m = _monster()
    out = screens.render_encounter(_cfg(tmp_path), m, line="gotcha soon")
    assert "gotcha soon" in open(out).read()


def test_render_encounter_never_raises(tmp_path):
    # a monster missing attributes -> swallowed, returns None
    assert screens.render_encounter(_cfg(tmp_path), object()) is None


# --- render_capture -------------------------------------------------------

def test_render_capture_frames(tmp_path):
    m = _monster()
    frames_new = screens.render_capture(_cfg(tmp_path / "a"), m, caught=True)
    assert frames_new
    assert len(frames_new) == 4
    # a caught sequence renders real frames and never the "no handshake" end card
    for fn in frames_new:
        assert open(fn).read()
    assert "NO HANDSHAKE" not in open(frames_new[-1]).read()


def test_render_capture_not_caught(tmp_path):
    m = _monster()
    frames = screens.render_capture(_cfg(tmp_path), m, caught=False)
    assert frames and "NO HANDSHAKE" in open(frames[-1]).read()


def test_render_capture_never_raises(tmp_path):
    assert screens.render_capture(_cfg(tmp_path), object(), caught=True) is None


# --- dojo_lines -----------------------------------------------------------

_ITEMS = [
    {"name": "OPTUS_A1B2", "level": 11, "encryption": "wpa2", "rarity": "", "kind": "wifi"},
    {"name": "Pixel 9", "level": 4, "encryption": "", "rarity": "legendary", "kind": "ble"},
]


def test_dojo_lines_with_targets():
    lines = screens.dojo_lines(_ITEMS, ready=2, cracked=5)
    assert lines[0] == "\n  == BATTLE DOJO ==   2 ready · 5 cracked"
    assert lines[1] == "  [A] AUTO BATTLE  — crack every fresh target  (`battle --all`)"
    assert lines[2] == "  [B] MANUAL       — pick one below            (`battle <name>`)"
    assert lines[3] == "\n  targets you haven't battled yet:"
    assert lines[4] == "    · OPTUS_A1B2             Lv11  WPA2"
    assert lines[5] == "    · Pixel 9                Lv4   LEGENDARY"
    assert lines[-1] == ("\n  device: OK opens · Up/Down move · OK select · Back exit")


def test_dojo_lines_no_targets():
    lines = screens.dojo_lines([], ready=0, cracked=0)
    assert "\n  No fresh targets — go catch some monsters first!" in lines
    assert not any("targets you haven't battled yet" in ln for ln in lines)


def test_dojo_lines_truncates_over_twelve():
    items = [{"name": f"m{i}", "level": i, "encryption": "wpa2", "rarity": "",
              "kind": "wifi"} for i in range(15)]
    lines = screens.dojo_lines(items, ready=15, cracked=0)
    assert "    … +3 more" in lines
    # only 12 target rows rendered
    rows = [ln for ln in lines if ln.startswith("    · ")]
    assert len(rows) == 12


class _FakeDex:
    def __init__(self, mons):
        self._m = mons

    def all(self):
        return self._m


def test_dojo_lines_matches_render_dojo_text(tmp_path):
    """Golden: the printed text block of commands._render_dojo (minus its
    ``[screen]`` render lines) equals dojo_lines printed line by line."""
    m = _monster()
    dex = _FakeDex([m])
    cfg = types.SimpleNamespace(
        character_variant="classic",
        battlemenu_html_out=str(tmp_path / "menu.html"),
        battlelist_html_out=str(tmp_path / "list.html"),
    )
    state = types.SimpleNamespace(stage="adult")

    buf = io.StringIO()
    with redirect_stdout(buf):
        commands._render_dojo(cfg, dex, None, state)
    original = [ln for ln in buf.getvalue().splitlines()
                if not ln.lstrip().startswith("[screen]")]

    # rebuild the same data the command layer feeds the pure helper
    from flippergotchi.game.monsters import label
    ready = commands._ready_targets(dex)
    cracked = sum(1 for x in dex.all()
                  if x.kind in ("wifi", "ble") and x.defeated)
    items = [{"name": label(x), "level": x.level,
              "encryption": x.encryption if x.kind == "wifi"
              else getattr(x, "pairing", ""),
              "rarity": x.rarity, "kind": x.kind} for x in ready]

    buf2 = io.StringIO()
    with redirect_stdout(buf2):
        for ln in screens.dojo_lines(items, len(ready), cracked):
            print(ln)
    rebuilt = buf2.getvalue().splitlines()

    assert rebuilt == original
