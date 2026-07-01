#!/usr/bin/env python3
"""shoot.py -- render a Flippergotchi screen's HTML the way the device would.

This is a DECISION-SUPPORT test harness (P1 item 7). It loads a screen's HTML in
a *headless WebKit* (the same engine the Flipper One runs on DRM; see
docs/flipper-one-implementation.md and docs/ui-render-through.md) at EXACTLY the
device's 256x144 viewport, deviceScaleFactor=1, screenshots it, and then pushes
the PNG through the device's 6-bit (64-level) grayscale panel -- WITH dithering,
because the review found that posterize-only truncation visibly bands the
gradients/blurred shadows every screen uses.

It is the closest faithful proxy we can run without hardware, and it also finally
commits the missing HTML->PNG step (the view layer only ever wrote .html to disk).

------------------------------------------------------------------------------
OPTIONAL DEPENDENCY -- this is NOT a package runtime dependency. Install it only
to run the harness (a dev/CI concern):

    pip install playwright pillow
    python -m playwright install webkit          # faithful: device uses WebKit
    # or, if WebKit's host libs are unavailable in your sandbox:
    python -m playwright install chromium         # fallback (see --browser)

  * WebKit is preferred because the device renders on headless WebKit-on-DRM;
    Chromium (Blink) is a convenient fallback but is NOT the device engine --
    treat Chromium output as indicative, not authoritative.
  * Floyd-Steinberg / ordered dithering uses numpy if present; without numpy it
    falls back to posterize-only and warns.
  * A Puppeteer/Node port would be equivalent; Playwright is used here because it
    bundles a pinned WebKit and a one-line install.
------------------------------------------------------------------------------

Examples:

    # Render the live face screen the app just wrote, dither, save PNG:
    python tools/shoot.py /tmp/flippergotchi/face.html

    # Every screen the app has written, into docs/_shots/, 4x upscaled preview:
    python tools/shoot.py -o docs/_shots --scale 4 /tmp/flippergotchi/*.html

    # From stdin, force Chromium, ordered dither:
    cat screen.html | python tools/shoot.py --browser chromium --dither ordered -

    # Raw (undithered, no grayscale) screenshot to eyeball the WebKit render:
    python tools/shoot.py --no-gray face.html
"""
from __future__ import annotations

import argparse
import os
import sys

# Device panel constants (verified: https://docs.flipper.net/one/general/tech-specs)
DEVICE_W = 256
DEVICE_H = 144
GRAY_BITS = 6                       # 6-bit panel -> 64 grey levels
GRAY_LEVELS = 1 << GRAY_BITS       # 64


# --------------------------------------------------------------------------- #
# Grayscale + dithering (device panel simulation)
# --------------------------------------------------------------------------- #
def _posterize(g):
    """Posterize an 'L' image to 6 bits -- mirrors tools/device_gray.py exactly
    (no dithering: shown for comparison and as the numpy-less fallback)."""
    from PIL import ImageOps
    return ImageOps.posterize(g, GRAY_BITS)


def _quantize_levels(value, levels=GRAY_LEVELS):
    step = 255.0 / (levels - 1)
    return round(value / step) * step


def _fs_dither(g):
    """Floyd-Steinberg error-diffusion down to 64 grey levels. Best for the
    smooth gradients/shadows the screens use -- breaks up the 64-level banding
    into fine noise instead of hard contour lines."""
    try:
        import numpy as np
    except ImportError:
        sys.stderr.write("shoot.py: numpy not found; falling back to posterize "
                         "(banding NOT simulated). pip install numpy\n")
        return _posterize(g)
    a = np.asarray(g, dtype=np.float32)
    h, w = a.shape
    step = 255.0 / (GRAY_LEVELS - 1)
    for y in range(h):
        for x in range(w):
            old = a[y, x]
            new = round(old / step) * step
            err = old - new
            a[y, x] = new
            if x + 1 < w:
                a[y, x + 1] += err * 7 / 16
            if y + 1 < h:
                if x > 0:
                    a[y + 1, x - 1] += err * 3 / 16
                a[y + 1, x] += err * 5 / 16
                if x + 1 < w:
                    a[y + 1, x + 1] += err * 1 / 16
    from PIL import Image
    return Image.fromarray(np.clip(a, 0, 255).astype("uint8"), "L")


# 8x8 Bayer matrix for ordered dithering (stable, no per-frame noise crawl --
# closer to how a fixed-pattern LCD dithers, and animation-friendly).
_BAYER8 = [
    [0, 32, 8, 40, 2, 34, 10, 42], [48, 16, 56, 24, 50, 18, 58, 26],
    [12, 44, 4, 36, 14, 46, 6, 38], [60, 28, 52, 20, 62, 30, 54, 22],
    [3, 35, 11, 43, 1, 33, 9, 41], [51, 19, 59, 27, 49, 17, 57, 25],
    [15, 47, 7, 39, 13, 45, 5, 37], [63, 31, 55, 23, 61, 29, 53, 21],
]


def _ordered_dither(g):
    """Ordered (Bayer 8x8) dithering to 64 grey levels."""
    try:
        import numpy as np
    except ImportError:
        sys.stderr.write("shoot.py: numpy not found; falling back to posterize "
                         "(banding NOT simulated). pip install numpy\n")
        return _posterize(g)
    from PIL import Image
    a = np.asarray(g, dtype=np.float32)
    h, w = a.shape
    step = 255.0 / (GRAY_LEVELS - 1)
    bayer = np.asarray(_BAYER8, dtype=np.float32)
    # normalise threshold to [-0.5, 0.5) of a quantisation step
    thresh = (np.tile(bayer, (h // 8 + 1, w // 8 + 1))[:h, :w] / 64.0 - 0.5) * step
    a = a + thresh
    a = np.round(a / step) * step
    return Image.fromarray(np.clip(a, 0, 255).astype("uint8"), "L")


_DITHERERS = {
    "floyd": _fs_dither,
    "ordered": _ordered_dither,
    "none": _posterize,
}


def device_gray(im, dither="floyd"):
    """One RGB/RGBA frame -> device 6-bit grayscale (RGB), optionally dithered."""
    g = im.convert("L")
    g = _DITHERERS[dither](g)
    return g.convert("RGB")


# --------------------------------------------------------------------------- #
# WebKit / Chromium screenshot
# --------------------------------------------------------------------------- #
def _load_html(source):
    """Return (html_string, label) for a file path or '-' (stdin)."""
    if source == "-":
        return sys.stdin.read(), "stdin"
    with open(source, "r", encoding="utf-8") as f:
        return f.read(), os.path.splitext(os.path.basename(source))[0]


def screenshot_html(html, browser="webkit", width=DEVICE_W, height=DEVICE_H):
    """Render `html` in headless WebKit (or Chromium) at exactly width x height,
    deviceScaleFactor=1, and return the raw PNG bytes.

    Tries the requested engine first, then the other, so the harness still runs
    in sandboxes where one engine's host libraries are missing (e.g. WebKit)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("shoot.py: playwright is not installed.\n"
                 "  pip install playwright && python -m playwright install webkit")

    order = [browser] + [b for b in ("webkit", "chromium") if b != browser]
    last_err = None
    with sync_playwright() as p:
        for engine in order:
            try:
                b = getattr(p, engine).launch()
            except Exception as e:              # engine binary/libs unavailable
                last_err = e
                continue
            try:
                page = b.new_page(
                    viewport={"width": width, "height": height},
                    device_scale_factor=1,
                )
                page.set_content(html, wait_until="networkidle")
                png = page.screenshot(clip={"x": 0, "y": 0,
                                            "width": width, "height": height})
                if engine != browser:
                    sys.stderr.write(f"shoot.py: '{browser}' unavailable; used "
                                     f"'{engine}' instead (NOT the device engine "
                                     f"if that is chromium)\n")
                return png
            finally:
                b.close()
    raise SystemExit(
        f"shoot.py: could not launch any browser engine ({order}). Last error:\n"
        f"  {last_err}\n"
        f"Install one: python -m playwright install webkit  (or chromium)")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _process(source, args):
    from io import BytesIO
    from PIL import Image

    html, label = _load_html(source)
    png = screenshot_html(html, browser=args.browser,
                          width=args.width, height=args.height)
    im = Image.open(BytesIO(png)).convert("RGB")

    if not args.no_gray:
        im = device_gray(im, dither=args.dither)

    if args.scale and args.scale != 1:
        im = im.resize((im.width * args.scale, im.height * args.scale),
                       Image.NEAREST)

    os.makedirs(args.out, exist_ok=True)
    suffix = "" if args.no_gray else f".{args.dither}"
    out_path = os.path.join(args.out, f"{label}{suffix}.png")
    im.save(out_path)
    print("shot", out_path)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Render a Flippergotchi screen HTML at 256x144 in headless "
                    "WebKit, then apply the device's 6-bit grayscale + dither.")
    ap.add_argument("inputs", nargs="+",
                    help="HTML file path(s), or '-' for stdin")
    ap.add_argument("-o", "--out", default=".", help="output directory")
    ap.add_argument("--browser", choices=("webkit", "chromium"), default="webkit",
                    help="engine (default webkit = device-faithful; falls back "
                         "to the other if unavailable)")
    ap.add_argument("--dither", choices=("floyd", "ordered", "none"),
                    default="floyd",
                    help="6-bit grayscale dithering (default floyd; 'none' = "
                         "posterize-only, matching tools/device_gray.py)")
    ap.add_argument("--no-gray", action="store_true",
                    help="skip grayscale/dither -- raw WebKit screenshot")
    ap.add_argument("--scale", type=int, default=1,
                    help="nearest-neighbour upscale the final PNG for viewing")
    ap.add_argument("--width", type=int, default=DEVICE_W)
    ap.add_argument("--height", type=int, default=DEVICE_H)
    args = ap.parse_args(argv)

    for source in args.inputs:
        _process(source, args)


if __name__ == "__main__":
    main()
