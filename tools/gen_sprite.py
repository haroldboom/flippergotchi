#!/usr/bin/env python3
"""Generate / derive Flippergotchi shark sprites with the Gemini image API.

The mascot sprites in flippergotchi/view/sprites/ were made with this. It reads
the API key from the GEMINI_API_KEY env var, or from ~/.gemini_api_key — the key
is NEVER stored in the repo. Pipeline: text-to-image (or image-to-image off a
reference for character consistency) -> key the checkerboard/background to true
alpha -> trim -> resize.

Usage:
  export GEMINI_API_KEY=...            # or put it in ~/.gemini_api_key
  python tools/gen_sprite.py "a cyberpunk pixel-art shark, transparent bg" out.png
  python tools/gen_sprite.py "recolor to gold" out.png --ref hero.png
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import urllib.request
from collections import deque

MODEL = "gemini-3-pro-image"


def _key() -> str:
    k = os.environ.get("GEMINI_API_KEY")
    if k:
        return k.strip()
    path = os.path.expanduser("~/.gemini_api_key")
    if os.path.exists(path):
        return open(path).read().strip()
    raise SystemExit("No API key: set GEMINI_API_KEY or write ~/.gemini_api_key")


def generate(prompt: str, out: str, ref_png: str | None = None, model: str = MODEL) -> bool:
    parts = [{"text": prompt}]
    if ref_png:
        b = base64.b64encode(open(ref_png, "rb").read()).decode()
        parts.append({"inlineData": {"mimeType": "image/png", "data": b}})
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
           f":generateContent?key={_key()}")
    req = urllib.request.Request(
        url, data=json.dumps({"contents": [{"parts": parts}],
                              "generationConfig": {"responseModalities": ["IMAGE"]}}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.loads(r.read().decode())
    for p in data.get("candidates", [{}])[0].get("content", {}).get("parts", []):
        if "inlineData" in p:
            open(out, "wb").write(base64.b64decode(p["inlineData"]["data"]))
            return True
    return False


def key_alpha(path: str, out: str | None = None):
    """Flood-fill the (often checkerboard) background to true transparency, trim."""
    import numpy as np
    from PIL import Image
    im = Image.open(path).convert("RGBA")
    a = np.array(im)
    h, w = a.shape[:2]
    rgb = a[:, :, :3].astype(int)
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]]).reshape(-1, 3)
    cols, counts = np.unique(border // 6 * 6, axis=0, return_counts=True)
    top = cols[np.argsort(-counts)[:3]]

    def isbg(y, x):
        p = rgb[y, x]
        return any(abs(p[0] - c[0]) + abs(p[1] - c[1]) + abs(p[2] - c[2]) < 55 for c in top)

    vis = np.zeros((h, w), bool)
    dq = deque()
    for x in range(w):
        for y in (0, h - 1):
            if not vis[y, x] and isbg(y, x):
                vis[y, x] = True
                dq.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if not vis[y, x] and isbg(y, x):
                vis[y, x] = True
                dq.append((y, x))
    while dq:
        y, x = dq.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and not vis[ny, nx] and isbg(ny, nx):
                vis[ny, nx] = True
                dq.append((ny, nx))
    a[vis, 3] = 0
    res = Image.fromarray(a)
    bb = res.getbbox()
    if bb:
        res = res.crop(bb)
    res.save(out or path)
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt")
    ap.add_argument("out")
    ap.add_argument("--ref", help="reference PNG for image-to-image")
    ap.add_argument("--no-key-alpha", action="store_true", help="skip background keying")
    ap.add_argument("--height", type=int, default=150, help="output height px")
    a = ap.parse_args()
    raw = a.out + ".raw.png"
    if not generate(a.prompt, raw, a.ref):
        raise SystemExit("no image returned")
    if a.no_key_alpha:
        os.replace(raw, a.out)
    else:
        im = key_alpha(raw)
        from PIL import Image
        H = a.height
        im = im.resize((max(1, int(im.width * H / im.height)), H), Image.LANCZOS)
        im.save(a.out, optimize=True)
        os.remove(raw)
    print("wrote", a.out)
