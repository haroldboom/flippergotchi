"""Shared worn-gear compositing for the character renders.

Both the live HUD (`flipctl.py`) and the equipment screen (`equip_screen.py`)
draw the equipped pieces ON the character using the SAME anchors, per-stage
nudge and per-rarity glow -- so gear sits identically wherever it's shown.
Keeping it in one place stops the two copies from drifting apart.

A piece's anchor is (left%, top%, width%, rotate-deg), as a fraction of the
character box (a `.charwrap` that is `height:82px` with auto width = the sprite's
width at that height). z-order is dict order: later entries paint in front.
"""
from __future__ import annotations

import base64
import os

_SPRITES = os.path.join(os.path.dirname(__file__), "sprites")
_cache: dict = {}


def _worn_b64(slot: str, rarity: str) -> str | None:
    key = f"worn/{slot}-{rarity}"
    if key not in _cache:
        path = os.path.join(_SPRITES, "worn", f"{slot}-{rarity}.png")
        if not os.path.exists(path):
            return None
        with open(path, "rb") as f:
            _cache[key] = base64.b64encode(f.read()).decode()
    return _cache[key]


# anchor on the forward-facing shark: (left%, top%, width%, rotate-deg).
#   helmet  -> crown sits centred on top of the head, just above the eyes
#   eyepiece-> HUD lens over the viewer-left eye
#   amulet  -> pendant hangs at the chest, below the mouth
#   fin     -> augment fin riding the back, behind the dorsal mohawk
#   weapon  -> glowing blade floats at the right flank, hilt low, blade up
# z-order (dict order): fin and weapon behind the head furniture, face last.
_WORN_ANCHOR = {
    "fin":      (49, 0, 32, 15),
    "weapon":   (70, 44, 40, -36),
    "helmet":   (26, -6, 49, 0),
    "eyepiece": (30, 33, 19, 0),
    "amulet":   (40, 80, 21, 0),
}
# per-stage nudge: heads sit at different heights/sizes. (top% delta, width scale)
_STAGE_ADJUST = {
    "hatchling": (16, 0.78),
    "fingerling": (7, 0.9),
    "juvenile": (2, 0.97),
    "adult": (0, 1.0),
    "alpha": (3, 1.05),
    "legend": (9, 1.04),
}
_RARITY = {"common": "#b8c2cb", "uncommon": "#7fd1a6", "rare": "#5aa9ff",
           "epic": "#c07bf0", "legendary": "#ffcf4d"}
# coloured glow for worn pieces by rarity (legendary strongest)
_GLOW = {
    "rare": "drop-shadow(0 0 2px #5aa9ff)",
    "epic": "drop-shadow(0 0 2.5px #c07bf0)",
    "legendary": "drop-shadow(0 0 2px #ffd24a) drop-shadow(0 0 4px #ffae1a)",
}

# CSS the host template must include for the worn overlay to animate/anchor.
CSS = (
    ".worn{position:absolute;}"
    ".leg{animation:legpulse 1.3s ease-in-out infinite;}"
    "@keyframes legpulse{0%,100%{filter:brightness(1)}50%{filter:brightness(1.35)}}"
)

_STAGES = tuple(_STAGE_ADJUST)


def stage_of(sprite: str) -> str:
    """Best-effort stage key from a sprite name like 'adult', 'blue-alpha'."""
    for part in sprite.replace("-", " ").split():
        if part in _STAGE_ADJUST:
            return part
    return "adult"


def html(equipped: dict, stage: str) -> str:
    """Build the <img class="worn"> overlay for `equipped` ({slot: rarity}).

    `stage` is the character's evolution stage (for the per-stage nudge).
    Legendary pieces pulse (the `.leg` class); rarer pieces get a glow.
    """
    dy, sc = _STAGE_ADJUST.get(stage, (0, 1.0))
    out = ""
    for slot, (L, T, Wd, rot) in _WORN_ANCHOR.items():
        r = (equipped or {}).get(slot)
        b = _worn_b64(slot, r) if r else None
        if not b:
            continue
        cls = "worn leg" if r == "legendary" else "worn"
        xform = f"rotate({rot}deg)" if rot else ""
        out += (f'<img class="{cls}" style="left:{L}%;top:{T + dy}%;'
                f'width:{Wd * sc}%;transform:{xform};'
                f'filter:{_GLOW.get(r, "none")}" '
                f'src="data:image/png;base64,{b}">')
    return out
