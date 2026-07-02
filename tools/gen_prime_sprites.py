#!/usr/bin/env python3
"""Derive the `prime` (L20) evolution-stage sprites from the `alpha` set.

PROGRAMMATICALLY-DERIVED PLACEHOLDER ART, pending final hand-drawn sprites.
`prime` sits between `adult` (L14) and `alpha` (L25); until an artist paints a
dedicated form, we derive it from alpha so it keeps the exact silhouette (and
therefore the shared worn-gear anchors) while reading as a clearly different,
not-yet-apex form. Re-run this script any time the alpha art changes:

    python3 tools/gen_prime_sprites.py

The "ion-charged" treatment (Pillow, deterministic, alpha-transparency kept):
  1. desaturate the original colours to ~40% (mutes alpha's gold/magenta),
  2. blend 60% toward a cool duotone ramp -- deep indigo shadows rising to
     pale ice-cyan highlights -- keyed off each pixel's luminance, so all the
     original shading/detail survives but the palette is unmistakably cooler,
  3. lift brightness ~1.12x with a slight contrast ease.
Step 3 matters most on-device: the Flipper HUD renders through
`filter:grayscale(1)`, so prime must differ in VALUE, not just hue -- it comes
out visibly lighter/softer than the dark, saturated alpha even in grayscale.

For every alpha-named sprite the matching prime file is written next to it:
  alpha.png            -> prime.png            (plus every alpha-<mood>.png)
  <variant>-alpha.png  -> <variant>-prime.png  (goblin/hammerhead/sawshark/whaleshark)
Sizes, RGBA mode and the alpha channel are preserved exactly.
"""
from __future__ import annotations

import os

from PIL import Image, ImageEnhance

SPRITES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "flippergotchi", "view", "sprites")

# duotone ramp endpoints (shadow -> highlight), applied by per-pixel luminance
_SHADOW = (22, 34, 74)      # deep indigo
_HILITE = (176, 233, 255)   # pale ice-cyan
_DESAT = 0.40               # keep 40% of the original saturation
_TINT = 0.60                # blend 60% toward the duotone ramp
_BRIGHT = 1.12              # value lift so it reads distinct in grayscale
_CONTRAST = 0.96


def derive_prime(src: Image.Image) -> Image.Image:
    """Apply the ion-charged prime treatment; preserves size + alpha channel."""
    src = src.convert("RGBA")
    rgb = src.convert("RGB")
    a = src.getchannel("A")
    # 1. mute the alpha-stage palette
    rgb = ImageEnhance.Color(rgb).enhance(_DESAT)
    # 2. cool duotone from luminance: shadow + (hilite - shadow) * L/255
    lum = src.convert("L")
    ramp = Image.merge("RGB", [
        lum.point([s + (h - s) * v // 255 for v in range(256)])
        for s, h in zip(_SHADOW, _HILITE)])
    rgb = Image.blend(rgb, ramp, _TINT)
    # 3. lighter, slightly eased -- the pre-apex form, not yet the dark alpha
    rgb = ImageEnhance.Brightness(rgb).enhance(_BRIGHT)
    rgb = ImageEnhance.Contrast(rgb).enhance(_CONTRAST)
    out = rgb.convert("RGBA")
    out.putalpha(a)  # transparency untouched
    return out


def alpha_to_prime_name(fname: str) -> str | None:
    """'alpha.png'->'prime.png', 'alpha-happy.png'->'prime-happy.png',
    'goblin-alpha.png'->'goblin-prime.png'; None if not an alpha sprite."""
    stem, ext = os.path.splitext(fname)
    if ext.lower() != ".png":
        return None
    parts = stem.split("-")
    if "alpha" not in parts:
        return None
    return "-".join("prime" if p == "alpha" else p for p in parts) + ext


def main() -> None:
    made = []
    for fname in sorted(os.listdir(SPRITES)):
        out_name = alpha_to_prime_name(fname)
        if not out_name:
            continue
        src = Image.open(os.path.join(SPRITES, fname))
        derive_prime(src).save(os.path.join(SPRITES, out_name), optimize=True)
        made.append(f"{fname} -> {out_name}")
    for line in made:
        print(line)
    print(f"wrote {len(made)} prime sprites to {SPRITES}")


if __name__ == "__main__":
    main()
