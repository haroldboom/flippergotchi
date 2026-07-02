"""The `prime` (L20) stage has its own DISTINCT sprite set.

Prime previously aliased onto the alpha sprites (`_STAGE_SPRITE_ALIAS`); it now
ships a full derived set (tools/gen_prime_sprites.py -- programmatically
derived placeholder art pending final hand-drawn sprites) so the
egg->hatchling->juvenile->adult->PRIME->alpha->legend ladder reads as a real
transformation. These tests pin: the files exist and are valid same-size RGBA
PNGs with real (non-transparent, alpha-distinct) content; the sprite lookup
resolves prime to `prime` files (never `alpha`); the mood/variant fallbacks
behave for prime exactly as they do for alpha; and a stage="prime" HUD render
doesn't crash.
"""
from __future__ import annotations

import os
import sys

import pytest
from PIL import Image, ImageChops, ImageStat

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flippergotchi.config import Config
from flippergotchi.pet.state import PetState
from flippergotchi.view import flipctl

SPRITES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "flippergotchi", "view", "sprites")

_VARIANTS = ["goblin", "hammerhead", "sawshark", "whaleshark"]
_MOOD_SET = ["", "chomp", "dmg1", "dmg2", "dmg3", "happy", "hungry", "hurt",
             "sleeping"]
# every prime file and the alpha file it was derived from
_PAIRS = ([("prime" + (f"-{m}" if m else ""), "alpha" + (f"-{m}" if m else ""))
           for m in _MOOD_SET]
          + [(f"{v}-prime", f"{v}-alpha") for v in _VARIANTS])


def _img(name: str) -> Image.Image:
    return Image.open(os.path.join(SPRITES, name + ".png"))


# --- the files exist and are sane RGBA art ----------------------------------

@pytest.mark.parametrize("prime,alpha", _PAIRS, ids=[p for p, _ in _PAIRS])
def test_prime_sprite_valid_rgba_same_size_as_alpha_source(prime, alpha):
    assert os.path.exists(os.path.join(SPRITES, prime + ".png")), \
        f"missing derived sprite {prime}.png (run tools/gen_prime_sprites.py)"
    p, a = _img(prime), _img(alpha)
    assert p.mode == "RGBA"
    assert p.size == a.size                      # size preserved from source
    # not blank: a real creature's worth of opaque pixels
    alpha_ch = p.getchannel("A")
    opaque = sum(alpha_ch.histogram()[129:])
    assert opaque > 1000, f"{prime}.png looks blank ({opaque} opaque px)"
    # transparency preserved exactly (same silhouette as the alpha source)
    assert ImageChops.difference(alpha_ch, a.convert("RGBA").getchannel("A")) \
        .getbbox() is None


def test_prime_is_visually_distinct_from_alpha_even_in_grayscale():
    # the HUD renders through filter:grayscale(1), so prime must differ in
    # VALUE, not just hue: mean opaque luminance shifts by a clear margin
    def mean_lum(name):
        im = _img(name).convert("RGBA")
        mask = im.getchannel("A").point(lambda v: 255 if v > 128 else 0)
        return ImageStat.Stat(im.convert("L"), mask=mask).mean[0]
    assert abs(mean_lum("prime") - mean_lum("alpha")) > 5


# --- sprite lookup: prime resolves to prime files, never alpha --------------

def test_prime_lookup_resolves_to_prime_not_alpha():
    assert flipctl._sprite_for("prime", "classic", "") == "prime"
    for v in _VARIANTS:
        assert flipctl._sprite_for("prime", v, "") == f"{v}-prime"


def test_prime_mood_and_damage_faces_resolve_like_alpha():
    for stage in ("prime", "alpha"):
        assert flipctl._sprite_for(stage, "classic", "happy") == f"{stage}-happy"
        assert flipctl._sprite_for(stage, "classic", "eating") == f"{stage}-chomp"
        assert flipctl._sprite_for(stage, "classic", "sick") == f"{stage}-hurt"
        assert flipctl._sprite_for(stage, "classic", "happy", 3) == f"{stage}-dmg3"


def test_prime_missing_mood_falls_back_like_alpha(monkeypatch):
    # a mood face with no art falls back to the base stage sprite -- simulate a
    # missing face file and check prime degrades exactly as alpha does
    real = flipctl._exists
    monkeypatch.setattr(
        flipctl, "_exists",
        lambda n: False if n.endswith("-sleeping") else real(n))
    assert flipctl._sprite_for("alpha", "classic", "sleeping") == "alpha"
    assert flipctl._sprite_for("prime", "classic", "sleeping") == "prime"
    # an unmapped mood also lands on the base sprite
    assert flipctl._sprite_for("prime", "classic", "curious") == "prime"


def test_prime_unknown_variant_falls_back_to_classic_like_alpha():
    # a variant with no per-stage art falls back to the classic stage sprite
    assert flipctl._sprite_for("prime", "megalodon", "") == "prime"
    assert flipctl._sprite_for("alpha", "megalodon", "") == "alpha"


# --- rendering at stage="prime" works end to end ----------------------------

@pytest.mark.parametrize("variant", ["classic"] + _VARIANTS)
def test_render_html_at_prime_stage_embeds_prime_sprite(variant):
    cfg = Config()
    cfg.character_variant = variant
    state = PetState(name="Flippy", level=20, stage="prime")
    html = flipctl.render_html(state, cfg)
    name = "prime" if variant == "classic" else f"{variant}-prime"
    with open(os.path.join(SPRITES, name + ".png"), "rb") as f:
        import base64
        b64 = base64.b64encode(f.read()).decode()
    assert b64 in html                     # the PRIME art, not the alpha art
    assert len(html) > 500                 # a real document came back
