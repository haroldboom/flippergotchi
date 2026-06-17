"""Visual feeding screen, authored at the Flipper One's native 256x144 (grayscale).

The pet on the left (chomping when just fed), a hunger/food bar, and the Larder's
contents listed on the right so the player can pick what to hand-feed. Reuses
flipctl's character-sprite helpers so the pet looks identical to the HUD. Scaled
up nearest-neighbour by the caller, same pipeline as the other screens.
"""
from __future__ import annotations

import html as _html
import os

from ..pet import mechanics
from . import flipctl
from ..game import food as food_mod


_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><style>
  html,body{{margin:0;background:#000;}}
  *{{box-sizing:border-box;image-rendering:pixelated;}}
  .screen{{filter:grayscale(1);image-rendering:pixelated;width:256px;height:144px;position:relative;
    overflow:hidden;font-family:'DejaVu Sans Mono',monospace;color:#eaf2ff;
    background:linear-gradient(#13213e 0%,#0d1730 55%,#0a1226 100%);}}
  .title{{position:absolute;top:5px;left:6px;font-size:9px;font-weight:800;
    letter-spacing:1px;color:#aee3ff;z-index:3;}}
  .char{{position:absolute;left:6px;bottom:30px;height:78px;z-index:2;
    filter:drop-shadow(0 2px 0 #0008);}}
  .plate{{position:absolute;left:8px;bottom:24px;width:84px;height:14px;border-radius:50%;
    background:radial-gradient(closest-side,#1c5a6e 0%,#123a4a 70%,transparent 100%);z-index:1;}}
  .bar{{position:absolute;left:6px;bottom:8px;width:96px;z-index:3;}}
  .bar .lbl{{font-size:7px;font-weight:800;color:#9fb6d6;}}
  .bar .track{{height:6px;background:#33405e;border:1px solid #223;border-radius:3px;overflow:hidden;}}
  .bar .fill{{height:100%;background:{foodcol};}}
  .pantry{{position:absolute;top:20px;right:6px;width:118px;z-index:3;}}
  .ph{{font-size:7px;font-weight:800;color:#9fb6d6;margin-bottom:2px;}}
  .row{{display:flex;justify-content:space-between;align-items:center;
    font-size:8px;font-weight:700;background:#0b1430cc;border:1px solid #2a3550;
    border-radius:2px;padding:1px 4px;margin-bottom:2px;}}
  .row.hot{{border-color:#ffd24a;color:#ffe79a;}}
  .row .q{{color:#7ddfff;font-weight:800;}}
  .empty{{font-size:8px;color:#6b7790;font-style:italic;}}
  .box{{position:absolute;left:4px;right:4px;bottom:4px;height:22px;background:#f6f1da;
    border:2px solid #39405a;border-radius:3px;display:flex;align-items:center;
    padding:2px 4px;z-index:5;color:#283044;}}
  .say{{font-size:8px;font-weight:700;line-height:1.1;}}
</style></head><body>
  <div class="screen">
    <div class="title">&#127828; FEED</div>
    <div class="plate"></div>
    <img class="char" src="data:image/png;base64,{sprite}"/>
    <div class="bar"><span class="lbl">FOOD</span>
      <div class="track"><div class="fill" style="width:{food}%"></div></div></div>
    <div class="pantry"><div class="ph">LARDER ({total}/{cap})</div>{rows}</div>
    <div class="box"><span class="say">{line}</span></div>
  </div>
</body></html>"""


def _food_color(pct: float) -> str:
    return "#58d858" if pct > 55 else "#f0c020" if pct > 25 else "#e85040"


def render(out_path: str, state, cfg, larder, eaten=None, line: str = "") -> str:
    """Render the feeding screen. ``larder`` is a game.larder.Larder; ``eaten`` is
    the food id just consumed (highlights the row + chomp face). Returns out_path."""
    path = os.path.expanduser(out_path)
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)

    variant = getattr(cfg, "character_variant", "classic")
    mood = "eating" if eaten else mechanics.mood(state)
    sprite = flipctl._sprite_b64(flipctl._sprite_for(state.stage, variant, mood))
    food_pct = int(max(0, min(100, 100 - state.hunger)))

    counts = larder.counts()
    rows = ""
    for fk in food_mod.all_kinds():
        n = counts.get(fk.id, 0)
        if not n:
            continue
        hot = " hot" if eaten == fk.id else ""
        rows += (f"<div class='row{hot}'><span>{_html.escape(fk.name)}</span>"
                 f"<span class='q'>x{n}</span></div>")
    if not rows:
        rows = "<div class='empty'>empty -- walk to forage food</div>"

    if not line:
        if eaten:
            fk = food_mod.get(eaten)
            line = f"Nom! {fk.name if fk else 'snack'} -- hunger down."
        elif counts:
            line = "Pick a food to feed:  feed <id>"
        else:
            line = "Larder's empty. Go for a walk to forage."

    body = _HTML.format(
        sprite=sprite, food=food_pct, foodcol=_food_color(food_pct),
        total=larder.total(), cap=larder.capacity, rows=rows,
        line=_html.escape(line))
    with open(path, "w") as f:
        f.write(body)
    return path
