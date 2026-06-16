from __future__ import annotations

import base64
import html as _html
import os

from ..pet import mechanics

# The screen is authored at the Flipper One's native 256x144 and meant to be
# scaled up with nearest-neighbour (see docs render pipeline) for a crisp,
# old-school 2D look. UI is a Pokemon-style HUD: cream boxes, HP bar, a bottom
# dialogue box. The mascot is a pre-rendered cyberpunk pixel sprite.
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


def _sprite_for(stage: str, variant: str) -> str:
    if variant and variant not in ("classic", "") and stage == "adult":
        return f"var-{variant}"
    return stage


def _hp_color(pct: float) -> str:
    return "#58d858" if pct > 50 else "#f0c020" if pct > 20 else "#e85040"


_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>{name}</title><style>
  html,body{{margin:0;background:#000;}}
  *{{box-sizing:border-box;image-rendering:pixelated;}}
  .screen{{width:256px;height:144px;position:relative;overflow:hidden;
    font-family:'DejaVu Sans Mono',monospace;color:#283044;
    background:linear-gradient(#13213e 0%,#0d1730 55%,#0a1226 100%);}}
  .platform{{position:absolute;left:50%;bottom:34px;transform:translateX(-50%);
    width:128px;height:26px;border-radius:50%;
    background:radial-gradient(closest-side,#1c5a6e 0%,#123a4a 70%,transparent 100%);
    box-shadow:0 0 0 1px #2ee9ff33;}}
  .mascot{{position:absolute;left:50%;bottom:40px;transform:translateX(-50%);
    height:96px;filter:drop-shadow(0 2px 0 #0008);}}
  .box{{position:absolute;background:#f6f1da;border:2px solid #39405a;border-radius:4px;
    box-shadow:inset 0 0 0 1px #ffffffcc, 0 1px 0 #00000066;padding:3px 5px;}}
  .hp{{top:5px;left:5px;width:150px;}}
  .row{{display:flex;justify-content:space-between;align-items:center;}}
  .nm{{font-size:11px;font-weight:800;letter-spacing:.5px;}}
  .lv{{font-size:9px;font-weight:800;}}
  .bar{{display:flex;align-items:center;gap:3px;margin-top:2px;}}
  .tag{{font-size:7px;font-weight:800;color:#fff;background:#c88018;border-radius:2px;padding:0 2px;}}
  .tag.x{{background:#3a7fd0;}}
  .track{{flex:1;height:5px;background:#5a6072;border:1px solid #2a3045;border-radius:2px;overflow:hidden;}}
  .fill{{height:100%;}}
  .sub{{font-size:7px;font-weight:700;color:#7a4a12;letter-spacing:1px;margin-top:1px;}}
  .fe{{top:5px;right:5px;width:74px;}}
  .fe .l{{font-size:7px;font-weight:800;width:18px;}}
  .dlg{{left:5px;right:5px;bottom:5px;height:30px;display:flex;align-items:center;}}
  .say{{font-size:9px;font-weight:700;line-height:1.15;}}
  .gear{{position:absolute;top:46px;right:6px;display:flex;flex-direction:column;gap:3px;}}
  .slot{{width:8px;height:8px;border:1px solid #0008;border-radius:2px;}}
</style></head><body>
  <div class="screen">
    <div class="platform"></div>
    <img class="mascot" src="data:image/png;base64,{sprite}"/>
    <div class="gear">{gear}</div>
    <div class="box hp">
      <div class="row"><span class="nm">{name}</span><span class="lv">:L{level}</span></div>
      <div class="bar"><span class="tag">HP</span><div class="track"><div class="fill" style="width:{health}%;background:{hpcol}"></div></div></div>
      <div class="bar"><span class="tag x">XP</span><div class="track"><div class="fill" style="width:{xp}%;background:#3a7fd0"></div></div></div>
      <div class="sub">{stage}</div>
    </div>
    <div class="box fe">
      <div class="bar"><span class="l">FOOD</span><div class="track"><div class="fill" style="width:{food}%;background:#e0863a"></div></div></div>
      <div class="bar"><span class="l">ENRG</span><div class="track"><div class="fill" style="width:{energy}%;background:#42c9d8"></div></div></div>
    </div>
    <div class="box dlg"><span class="say">{name}: {line}</span></div>
  </div>
</body></html>"""

_RARITY = {"common": "#b8c2cb", "uncommon": "#7fd1a6", "rare": "#5aa9ff",
           "epic": "#c07bf0", "legendary": "#ffcf4d"}


def render(state, cfg, line: str = "", mood_override: str | None = None,
           equipped: dict | None = None) -> str:
    path = os.path.expanduser(cfg.flipctl_html_out)
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    variant = getattr(cfg, "mascot_variant", "classic")
    nxt = mechanics.xp_to_next(state.level, cfg)
    health = int(max(0, min(100, state.health)))
    gear = "".join(
        f'<div class="slot" style="background:{_RARITY.get(r, "#b8c2cb")}"></div>'
        for r in (equipped or {}).values())
    html = _HTML.format(
        name=_html.escape(state.name), level=state.level,
        stage=_html.escape(state.stage.upper()),
        sprite=_sprite_b64(_sprite_for(state.stage, variant)), gear=gear,
        health=health, hpcol=_hp_color(health),
        energy=int(max(0, state.energy)),
        food=int(max(0, min(100, 100 - state.hunger))),
        xp=int(max(0, min(100, state.xp / nxt * 100))) if nxt else 0,
        line=_html.escape(f'"{line}"') if line else "",
    )
    with open(path, "w") as f:
        f.write(html)
    return path
