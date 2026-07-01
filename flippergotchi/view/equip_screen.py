"""Visual equipment/inventory screen: the character WEARING its equipped gear on
the left, a list of the five slots on the right, and a PvP-power
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
from . import sink
from . import worn as worn_mod
from .worn import _RARITY

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


_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Equipment</title><style>
  html,body{{margin:0;background:#000;}}
  *{{box-sizing:border-box;image-rendering:pixelated;}}
  .screen{{filter:grayscale(1);image-rendering:pixelated;width:256px;height:144px;position:relative;overflow:hidden;
    font-family:'DejaVu Sans Mono',monospace;color:#283044;
    background:linear-gradient(#13213e 0%,#0d1730 55%,#0a1226 100%);}}
  .platform{{position:absolute;left:60px;bottom:30px;transform:translateX(-50%);
    width:96px;height:20px;border-radius:50%;
    background:radial-gradient(closest-side,#1c5a6e 0%,#123a4a 70%,transparent 100%);}}
  .charwrap{{position:absolute;left:60px;bottom:33px;transform:translateX(-50%);
    height:82px;display:inline-block;z-index:1;
    filter:drop-shadow(0 2px 0 #0008);}}
  .character{{height:82px;display:block;position:relative;z-index:2;}}
  .worn{{position:absolute;z-index:3;}}
  .worn.back{{z-index:1;}}
  .leg{{animation:legpulse 1.3s ease-in-out infinite;}}
  @keyframes legpulse{{0%,100%{{filter:brightness(1)}}50%{{filter:brightness(1.35)}}}}
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


def render_html(inv, character_sprite: str = "adult") -> str:
    """Build the 256x144 equipment screen for `inv` (a game.equipment.Inventory)
    as a string (pure; no I/O).

    The character `character_sprite` is drawn wearing its equipped pieces, with a
    cream box per slot on the right and a PvP-power footer.
    """
    # worn gear: overlay each equipped piece on the character (shared anchors so
    # gear sits identically here and on the live HUD).
    equipped = {slot: it.rarity
                for slot in SLOTS
                for it in [inv.items.get(inv.equipped.get(slot))] if it}
    worn = worn_mod.html(equipped, worn_mod.stage_of(character_sprite),
                         worn_mod.variant_of(character_sprite))

    # one cream retro box per slot, in canonical SLOTS order
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
    return html


def render(out_path: str, inv, character_sprite: str = "adult") -> str:
    """Write a 256x144 equipment screen for `inv`. Returns out_path."""
    return sink.write(out_path, render_html(inv, character_sprite))
