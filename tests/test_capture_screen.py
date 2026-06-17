"""The visual net-gun capture animation: deauth/capture HUD, both outcomes,
and the user-set capture timeout surfaced in the frames."""
from __future__ import annotations

import os

from flippergotchi.view import capture_screen


def test_success_sequence_writes_four_frames(tmp_path):
    paths = capture_screen.render_sequence(
        str(tmp_path), {"species": "Crypterion", "name": "OPTUS_A1B2"},
        caught=True, deauth=5, timeout=20)
    assert len(paths) == 4
    assert all(os.path.exists(p) for p in paths)
    last = open(paths[-1]).read()
    assert "GOTCHA!" in last and "captured" in last
    # the species sprite (not the fallback) is embedded
    from flippergotchi.view import monster_art
    assert monster_art.sprite_b64("Crypterion") in last


def test_background_deauth_and_capture_hud(tmp_path):
    paths = capture_screen.render_sequence(
        str(tmp_path), {"species": "Wavemon", "name": "Net"}, deauth=7, timeout=20)
    assert "DEAUTH x7" in open(paths[1]).read()           # deauth beat HUD
    assert "CAPTURE EAPOL" in open(paths[2]).read()        # capture beat HUD


def test_no_handshake_failure_outcome(tmp_path):
    paths = capture_screen.render_sequence(
        str(tmp_path), {"species": "Wispling", "name": "DemoNet"},
        caught=False, timeout=30)
    last = open(paths[-1]).read()
    assert "NO HANDSHAKE" in last
    assert "timed out after 30s" in last                   # the timeout is shown


def test_timeout_is_user_configurable_in_frames(tmp_path):
    paths = capture_screen.render_sequence(
        str(tmp_path), {"species": "Rustbug", "name": "x"}, timeout=45)
    assert "~45s" in open(paths[2]).read()                 # capture beat shows it


def test_frames_have_no_unfilled_placeholders(tmp_path):
    paths = capture_screen.render_sequence(
        str(tmp_path), {"species": "Rustbug", "name": "x"}, caught=True)
    for p in paths:
        html = open(p).read()
        assert "__CSS__" not in html
        assert "{" not in html.split("<style>")[1].split("</style>")[1]
