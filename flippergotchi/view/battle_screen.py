from __future__ import annotations

import base64
import html as _html
import os

# Screen authored at the Flipper One's native 256x144, scaled up nearest-neighbour
# (see docs render pipeline) for a crisp retro look. A classic creature-collector PvP
# duel: the opponent stands upper-right with their HUD box upper-left, the player
# stands lower-left (mirrored so the two face off) with their HUD box lower-right,
# and a full-width cream dialogue box narrates the move along the bottom.
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


def _hp_color(pct: float) -> str:
    return "#58d858" if pct > 50 else "#f0c020" if pct > 20 else "#e85040"


_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>{tname} vs {yname}</title><style>
  html,body{{margin:0;background:#000;}}
  *{{box-sizing:border-box;image-rendering:pixelated;}}
  .screen{{filter:grayscale(1);image-rendering:pixelated;width:256px;height:144px;position:relative;overflow:hidden;
    font-family:'DejaVu Sans Mono',monospace;color:#283044;
    background:linear-gradient(#13213e 0%,#0d1730 55%,#0a1226 100%);}}
  .platform{{position:absolute;width:104px;height:20px;border-radius:50%;
    background:radial-gradient(closest-side,#1c5a6e 0%,#123a4a 70%,transparent 100%);}}
  .plat-them{{right:6px;top:46px;}}
  .plat-you{{left:6px;bottom:30px;}}
  .charwrap{{position:absolute;height:74px;display:inline-block;z-index:1;
    filter:drop-shadow(0 2px 0 #0008);}}
  .them{{right:18px;top:8px;}}
  .you{{left:18px;bottom:30px;transform:scaleX(-1);}}
  .character{{height:74px;display:block;}}
  .box{{position:absolute;background:#f6f1da;border:2px solid #39405a;border-radius:3px;
    box-shadow:inset 0 0 0 1px #ffffffcc;padding:2px 4px;z-index:3;}}
  .hp{{width:104px;}}
  .hp-them{{top:6px;left:4px;}}
  .hp-you{{bottom:32px;right:4px;}}
  .row{{display:flex;justify-content:space-between;align-items:center;gap:3px;}}
  .nm{{font-size:9px;font-weight:800;letter-spacing:.3px;}}
  .lv{{font-size:8px;font-weight:800;}}
  .bar{{display:flex;align-items:center;gap:2px;margin-top:1px;}}
  .tag{{font-size:6px;font-weight:800;color:#fff;background:#c88018;border-radius:2px;padding:0 2px;}}
  .track{{flex:1;height:5px;background:#5a6072;border:1px solid #2a3045;border-radius:2px;overflow:hidden;}}
  .fill{{height:100%;}}
  .dlg{{left:4px;right:4px;bottom:4px;height:24px;display:flex;align-items:center;}}
  .say{{font-size:8px;font-weight:700;line-height:1.1;}}
</style></head><body>
  <div class="screen">
    <div class="platform plat-them"></div>
    <div class="platform plat-you"></div>
    <div class="charwrap them"><img class="character" src="data:image/png;base64,{tsprite}"/></div>
    <div class="charwrap you"><img class="character" src="data:image/png;base64,{ysprite}"/></div>
    <div class="box hp hp-them">
      <div class="row"><span class="nm">{tname}</span><span class="lv">:L{tlevel}</span></div>
      <div class="bar"><span class="tag">HP</span><div class="track"><div class="fill" style="width:{thealth}%;background:{thpcol}"></div></div></div>
    </div>
    <div class="box hp hp-you">
      <div class="row"><span class="nm">{yname}</span><span class="lv">:L{ylevel}</span></div>
      <div class="bar"><span class="tag">HP</span><div class="track"><div class="fill" style="width:{yhealth}%;background:{yhpcol}"></div></div></div>
    </div>
    <div class="box dlg"><span class="say">{line}</span></div>
  </div>
</body></html>"""


def render(out_path: str, you: dict, them: dict, line: str = "") -> str:
    path = os.path.expanduser(out_path)
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    yhealth = int(max(0, min(100, you.get("health", 0))))
    thealth = int(max(0, min(100, them.get("health", 0))))
    html = _HTML.format(
        yname=_html.escape(str(you.get("name", ""))), ylevel=you.get("level", 0),
        ysprite=_sprite_b64(you.get("sprite", "adult")),
        yhealth=yhealth, yhpcol=_hp_color(yhealth),
        tname=_html.escape(str(them.get("name", ""))), tlevel=them.get("level", 0),
        tsprite=_sprite_b64(them.get("sprite", "adult")),
        thealth=thealth, thpcol=_hp_color(thealth),
        line=_html.escape(line) if line else "",
    )
    with open(path, "w") as f:
        f.write(html)
    return path
