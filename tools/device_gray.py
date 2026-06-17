#!/usr/bin/env python3
"""Convert renders to the Flipper One's actual screen: 64-level (6-bit) grayscale.

The panel is a monochrome LCD (256x144, grayscale 64 levels). Our source sprites
are colour, and the on-screen view templates already apply `filter:grayscale(1)`;
this helper posterizes any rendered PNG/GIF (including the Pillow-composited
showcases) to 6-bit grayscale so the docs match what the device shows.

    python tools/device_gray.py docs/*.png docs/*.gif
"""
from __future__ import annotations

import sys

from PIL import Image, ImageOps, ImageSequence


def device_gray(im: Image.Image) -> Image.Image:
    """One frame -> 6-bit (64-level) grayscale, returned as RGB."""
    g = im.convert("L")
    g = ImageOps.posterize(g, 6)        # 6 bits -> 64 grey levels
    return g.convert("RGB")


def convert(path: str) -> None:
    im = Image.open(path)
    if getattr(im, "is_animated", False):
        frames = [device_gray(f.convert("RGB")) for f in ImageSequence.Iterator(im)]
        durs = []
        im.seek(0)
        for f in ImageSequence.Iterator(im):
            durs.append(f.info.get("duration", 120))
        frames[0].save(path, save_all=True, append_images=frames[1:],
                       duration=durs, loop=0, optimize=True)
    else:
        device_gray(im).save(path)
    print("grayscaled", path)


if __name__ == "__main__":
    for p in sys.argv[1:]:
        convert(p)
