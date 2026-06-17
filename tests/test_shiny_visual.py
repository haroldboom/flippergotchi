"""Shiny monsters get a real visual treatment on the sprite itself (not just a
text tag): a brightness/contrast + outline-glow filter class plus animated
sparkle glints, on both the encounter card and the net-gun capture frames.
Non-shiny monsters render exactly as before (no shiny markers)."""
from __future__ import annotations

from flippergotchi.view import capture_screen, encounter_screen


def test_encounter_shiny_sprite_markers(tmp_path):
    out = encounter_screen.render(str(tmp_path / "enc.html"), {
        "species": "Crypterion", "name": "OPTUS_A1B2", "level": 11,
        "encryption": "wpa2", "defense": 72, "kind": "wifi", "shiny": True})
    html = open(out).read()
    # the sprite carries the shiny filter class and there are sparkle glints
    assert 'class="mon shiny"' in html
    assert 'class="glint"' in html
    assert "@keyframes shimmer" in html and "@keyframes twinkle" in html
    # the text tag still shows too
    assert "SHINY" in html


def test_encounter_non_shiny_has_no_markers(tmp_path):
    out = encounter_screen.render(str(tmp_path / "enc.html"), {
        "species": "Crypterion", "name": "OPTUS_A1B2", "level": 11,
        "encryption": "wpa2", "defense": 72, "kind": "wifi"})
    html = open(out).read()
    # the live sprite element is plain (CSS rules for .shiny may still be defined,
    # but nothing on the page uses them)
    assert 'class="mon"' in html           # plain sprite, no shiny class
    assert 'class="mon shiny"' not in html
    assert 'class="glint"' not in html
    assert "SHINY" not in html             # no shiny text tag either


def test_capture_shiny_frames_carry_treatment(tmp_path):
    paths = capture_screen.render_sequence(
        str(tmp_path), {"species": "Crypterion", "name": "OPTUS_A1B2",
                        "shiny": True}, caught=True, timeout=20)
    for p in paths:
        html = open(p).read()
        assert "class='mon shiny'" in html
        assert "class='glint'" in html
        assert "@keyframes shimmer" in html


def test_capture_non_shiny_frames_unchanged(tmp_path):
    paths = capture_screen.render_sequence(
        str(tmp_path), {"species": "Crypterion", "name": "OPTUS_A1B2"},
        caught=True, timeout=20)
    for p in paths:
        html = open(p).read()
        assert "class='mon'" in html
        assert "class='mon shiny'" not in html
        assert "class='glint'" not in html
    # still a working sequence
    assert "GOTCHA!" in open(paths[-1]).read()
