"""Visual equipment/inventory screen: the character WEARING its equipped gear on
the left, a Pokemon-style list of the five slots on the right, and a PvP-power
footer. Authored at the Flipper One's native 256x144 and scaled up nearest-
neighbour by the caller for a crisp retro look (same pipeline as flipctl).

The character composites its worn pieces exactly like flipctl.render does --
same per-slot anchors, per-stage nudge, and per-rarity glow.
"""
from __future__ import annotations

import base64
import html as _html
import os

from ..game.equipment import SLOTS

_SPRITES = os.path.join(os.path.dirname(__file__), "sprites")
_cache: dict = {}


def _sprite_b64(name: str) -> str:
    if name not in _cache:
        path = os.path.join(_SPRITES, name + ".png")
        if not os.path.exists(path):
            path = os.path.join(_SPRITES, "adult.png")
        with open(path, "rb") as f:
            _cache[name] = base64.b64encode(f.read()).decode()
    return _cache[name]


def _worn_b64(slot: str, rarity: str) -> str | None:
    key = f"worn/{slot}-{rarity}"
    if key not in _cache:
        path = os.path.join(_SPRITES, "worn", f"{slot}-{rarity}.png")
        if not os.path.exists(path):
            return None
        with open(path, "rb") as f:
            _cache[key] = base64.b64encode(f.read()).decode()
    return _cache[key]


def _stage_of(sprite: str) -> str:
    """Best-effort stage key for the worn-piece nudge, from a sprite name like
    'adult', 'blue-alpha' or 'legend-happy'."""
    for part in sprite.replace("-", " ").split():
        if part in _STAGE_ADJUST:
            return part
    return "adult"


# --- replicated from flipctl (kept identical so gear sits the same on screen) ---
# where each worn piece sits over the character box: (left%, top%, width%).
# z-order is the dict order (later = in front).
_WORN_ANCHOR = {
    "weapon":   (-16, 42, 42),
    "fin":      (40, -15, 26),
    "helmet":   (27, -9, 46),
    "eyepiece": (42, 30, 17),
    "amulet":   (41, 64, 18),
}
# per-stage nudge for the worn pieces (their heads sit at different heights/sizes):
# (top% delta, width scale)
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


_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Equipment</title><style>
  html,body{{margin:0;background:#000;}}
  *{{box-sizing:border-box;image-rendering:pixelated;}}
  .screen{{width:256px;height:144px;position:relative;overflow:hidden;
    font-family:'DejaVu Sans Mono',monospace;color:#283044;
    background:linear-gradient(#13213e 0%,#0d1730 55%,#0a1226 100%);}}
  .platform{{position:absolute;left:60px;bottom:30px;transform:translateX(-50%);
    width:96px;height:20px;border-radius:50%;
    background:radial-gradient(closest-side,#1c5a6e 0%,#123a4a 70%,transparent 100%);}}
  .charwrap{{position:absolute;left:60px;bottom:33px;transform:translateX(-50%);
    height:82px;display:inline-block;z-index:1;
    filter:drop-shadow(0 2px 0 #0008);}}
  .character{{height:82px;display:block;}}
  .worn{{position:absolute;}}
  .leg{{animation:legpulse 1.3s ease-in-out infinite;transform-origin:center;}}
  @keyframes legpulse{{0%,100%{{transform:scale(1)}}50%{{transform:scale(1.08)}}}}
  .title{{position:absolute;top:4px;left:4px;font-size:8px;font-weight:800;
    letter-spacing:.5px;color:#aee3ff;text-shadow:0 1px 0 #0009;z-index:3;}}
  .slots{{position:absolute;top:15px;right:4px;width:128px;
    display:flex;flex-direction:column;gap:2px;z-index:3;}}
  .box{{background:#f6f1da;border:2px solid #39405a;border-radius:3px;
    box-shadow:inset 0 0 0 1px #ffffffcc;padding:1px 4px;}}
  .srow{{display:flex;justify-content:space-between;align-items:center;gap:3px;}}
  .sl{{font-size:6px;font-weight:800;text-transform:uppercase;letter-spacing:.3px;
    color:#5a6072;}}
  .rar{{font-size:6px;font-weight:800;color:#fff;border-radius:2px;padding:0 2px;}}
  .inm{{font-size:8px;font-weight:800;line-height:1.1;
    overflow:hidden;white-space:nowrap;text-overflow:ellipsis;}}
  .bon{{font-size:6px;font-weight:800;color:#39405a;}}
  .empty{{font-size:8px;font-weight:700;color:#9aa0ad;font-style:italic;}}
  .foot{{position:absolute;left:4px;right:4px;bottom:4px;height:14px;
    display:flex;align-items:center;justify-content:center;z-index:3;}}
  .foot .box{{width:100%;height:100%;display:flex;align-items:center;
    justify-content:center;}}
  .pw{{font-size:8px;font-weight:800;letter-spacing:.4px;}}
  .pw b{{color:#c2402a;font-size:9px;}}
</style></head><body>
  <div class="screen">
    <div class="platform"></div>
    <div class="charwrap"><img class="character" src="data:image/png;base64,{sprite}"/>{worn}</div>
    <div class="title">EQUIP</div>
    <div class="slots">{slots}</div>
    <div class="foot"><div class="box"><span class="pw">PvP POWER&nbsp;&nbsp;<b>{power}</b></span></div></div>
  </div>
</body></html>"""


def render(out_path: str, inv, character_sprite: str = "adult") -> str:
    """Write a 256x144 equipment screen for `inv` (a game.equipment.Inventory).

    The character `character_sprite` is drawn wearing its equipped pieces, with a
    cream box per slot on the right and a PvP-power footer. Returns out_path.
    """
    path = os.path.expanduser(out_path)
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)

    # worn gear: overlay each equipped piece on the character at its slot anchor,
    # nudged per evolution stage. Higher rarities glow; legendary pulses.
    worn = ""
    stage = _stage_of(character_sprite)
    dy, sc = _STAGE_ADJUST.get(stage, (0, 1.0))
    for slot, (L, T, Wd) in _WORN_ANCHOR.items():
        iid = inv.equipped.get(slot)
        it = inv.items.get(iid) if iid else None
        r = it.rarity if it else None
        b = _worn_b64(slot, r) if r else None
        if b:
            cls = "worn leg" if r == "legendary" else "worn"
            worn += (f'<img class="{cls}" style="left:{L}%;top:{T + dy}%;'
                     f'width:{Wd * sc}%;filter:{_GLOW.get(r, "none")}" '
                     f'src="data:image/png;base64,{b}">')

    # one cream Pokemon-style box per slot, in canonical SLOTS order
    slots = ""
    for slot in SLOTS:
        iid = inv.equipped.get(slot)
        it = inv.items.get(iid) if iid else None
        if it:
            col = _RARITY.get(it.rarity, "#b8c2cb")
            bonus = (f'+{it.bonus_val:g} {it.bonus_stat.upper()}'
                     if it.bonus_stat else f'+{it.power} POW')
            slots += (
                f'<div class="box">'
                f'<div class="srow"><span class="sl">{_html.escape(slot)}</span>'
                f'<span class="rar" style="background:{col}">'
                f'{_html.escape(it.rarity.upper())}</span></div>'
                f'<div class="srow"><span class="inm">{_html.escape(it.name)}</span>'
                f'<span class="bon">{_html.escape(bonus)}</span></div></div>')
        else:
            slots += (
                f'<div class="box"><div class="srow">'
                f'<span class="sl">{_html.escape(slot)}</span>'
                f'<span class="empty">(empty)</span></div></div>')

    html = _HTML.format(
        sprite=_sprite_b64(character_sprite),
        worn=worn, slots=slots, power=inv.gear_power(),
    )
    with open(path, "w") as f:
        f.write(html)
    return path
