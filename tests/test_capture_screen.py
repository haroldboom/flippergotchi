"""The visual net-gun capture animation renders its frame sequence."""
from __future__ import annotations

import os

from flippergotchi.view import capture_screen


def test_success_sequence_writes_four_frames(tmp_path):
    paths = capture_screen.render_sequence(
        str(tmp_path), {"species": "Crypterion", "name": "OPTUS_A1B2"}, caught=True)
    assert len(paths) == 4
    assert all(os.path.exists(p) for p in paths)
    last = open(paths[-1]).read()
    assert "GOTCHA!" in last
    assert "netted" in last
    # the species sprite is embedded (not just the fallback)
    from flippergotchi.view import monster_art
    assert monster_art.sprite_b64("Crypterion") in last


def test_miss_sequence_ends_in_got_away(tmp_path):
    paths = capture_screen.render_sequence(
        str(tmp_path), {"species": "Wispling", "name": "DemoNet"}, caught=False)
    last = open(paths[-1]).read()
    assert "GOT AWAY!" in last and "broke free" in last


def test_frames_have_no_unfilled_placeholders(tmp_path):
    paths = capture_screen.render_sequence(
        str(tmp_path), {"species": "Rustbug", "name": "x"}, caught=True)
    for p in paths:
        html = open(p).read()
        assert "__CSS__" not in html       # CSS marker was substituted
        assert "{" not in html.split("<style>")[1].split("</style>")[1]  # body clean
