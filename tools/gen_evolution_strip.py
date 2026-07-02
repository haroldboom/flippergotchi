#!/usr/bin/env python3
"""Regenerate docs/evolutions.png: the full evolution ladder as a grayscale strip.

Composited straight from the real stage sprites (view/sprites/<stage>.png) so it
always matches the current STAGES ladder -- run after adding/retiring a stage.

    python3 tools/gen_evolution_strip.py

Grayscale to match the device panel (sprites ship colour, desaturated for the
64-level LCD). Requires Pillow (the `tools`/`dev` extra).
"""
from __future__ import annotations

import os
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPRITES = os.path.join(ROOT, "flippergotchi", "view", "sprites")
OUT = os.path.join(ROOT, "docs", "evolutions.png")

# (stage sprite name, label, unlock level) -- mirrors pet/mechanics.STAGES
STAGES = [
    ("egg", "egg", 1), ("hatchling", "hatchling", 2), ("juvenile", "juvenile", 8),
    ("adult", "adult", 14), ("prime", "prime", 20), ("alpha", "alpha", 25),
    ("legend", "legend", 40),
]

CELL_W, H, SPRITE_MAX_H = 210, 340, 190
BG = (17, 17, 17)


def _font(size):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def main():
    canvas = Image.new("RGB", (CELL_W * len(STAGES), H), BG)
    draw = ImageDraw.Draw(canvas)
    label_f, lvl_f = _font(30), _font(20)
    for i, (name, label, lvl) in enumerate(STAGES):
        spr = Image.open(os.path.join(SPRITES, f"{name}.png")).convert("RGBA")
        if spr.height > SPRITE_MAX_H:
            r = SPRITE_MAX_H / spr.height
            spr = spr.resize((int(spr.width * r), SPRITE_MAX_H), Image.LANCZOS)
        # desaturate to grayscale, preserve alpha (device is a mono panel)
        gray = ImageOps.grayscale(spr).convert("RGBA")
        gray.putalpha(spr.getchannel("A"))
        cx = i * CELL_W + CELL_W // 2
        canvas.paste(gray, (cx - gray.width // 2, 40 + (SPRITE_MAX_H - gray.height) // 2), gray)
        for text, f, y, fill in ((label, label_f, H - 62, (235, 235, 235)),
                                 (f"Lv{lvl}", lvl_f, H - 28, (150, 150, 150))):
            w = draw.textlength(text, font=f)
            draw.text((cx - w / 2, y), text, font=f, fill=fill)
    canvas.save(OUT)
    print(f"wrote {OUT}  ({canvas.size[0]}x{canvas.size[1]}, {len(STAGES)} stages)")


if __name__ == "__main__":
    main()
