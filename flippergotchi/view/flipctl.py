from __future__ import annotations

import base64
import html as _html
import os

from ..pet import mechanics

# Screen authored at the Flipper One's native 256x144, scaled up nearest-neighbour
# (see docs render pipeline) for a crisp retro look. Old-school Pokemon-style HUD
# with compact corner boxes (kept small so they don't cover the mascot). The
# mascot is a pre-rendered cyberpunk pixel sprite that SWAPS by action/mood
# (Pwnagotchi-style "the image just changes").
_SPRITES = os.path.join(os.path.dirname(__file__), "sprites")
_cache: dict = {}

# mood/action -> adult expression sprite suffix (only the classic adult has the
# full expression set; other stages/variants use their single sprite)
_MOOD_SPRITE = {
    "happy": "happy", "excited": "chomp", "eating": "chomp",
    "hungry": "hungry", "tired": "sleeping", "sleeping": "sleeping", "sick": "hurt",
}


def _sprite_b64(name: str) -> str:
    if name not in _cache:
        path = os.path.join(_SPRITES, name + ".png")
        if not os.path.exists(path):
            path = os.path.join(_SPRITES, "adult.png")
        with open(path, "rb") as f:
            _cache[name] = base64.b64encode(f.read()).decode()
    return _cache[name]


def _gear_icon_b64(slot: str) -> str:
    key = f"gear/{slot}"
    if key not in _cache:
        path = os.path.join(_SPRITES, "gear", slot + ".png")
        with open(path, "rb") as f:
            _cache[key] = base64.b64encode(f.read()).decode()
    return _cache[key]


def _sprite_for(stage: str, variant: str, mood: str) -> str:
    # a chosen colour variant (adult) overrides the action face
    if variant not in ("classic", "") and stage == "adult":
        return f"var-{variant}"
    # action/mood face for this stage, if that sprite exists (egg has none)
    m = _MOOD_SPRITE.get(mood)
    if m:
        cand = f"{stage}-{m}"
        if os.path.exists(os.path.join(_SPRITES, cand + ".png")):
            return cand
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
  .platform{{position:absolute;left:50%;bottom:30px;transform:translateX(-50%);
    width:120px;height:22px;border-radius:50%;
    background:radial-gradient(closest-side,#1c5a6e 0%,#123a4a 70%,transparent 100%);}}
  .mascot{{position:absolute;left:50%;bottom:33px;transform:translateX(-50%);
    height:82px;filter:drop-shadow(0 2px 0 #0008);z-index:1;}}
  .box{{position:absolute;background:#f6f1da;border:2px solid #39405a;border-radius:3px;
    box-shadow:inset 0 0 0 1px #ffffffcc;padding:2px 4px;z-index:3;}}
  .hp{{top:4px;left:4px;width:96px;}}
  .row{{display:flex;justify-content:space-between;align-items:center;gap:3px;}}
  .nm{{font-size:9px;font-weight:800;letter-spacing:.3px;}}
  .lv{{font-size:8px;font-weight:800;}}
  .bar{{display:flex;align-items:center;gap:2px;margin-top:1px;}}
  .tag{{font-size:6px;font-weight:800;color:#fff;background:#c88018;border-radius:2px;padding:0 2px;}}
  .tag.x{{background:#3a7fd0;}}
  .track{{flex:1;height:4px;background:#5a6072;border:1px solid #2a3045;border-radius:2px;overflow:hidden;}}
  .fill{{height:100%;}}
  .fe{{top:4px;right:4px;width:58px;}}
  .fe .l{{font-size:6px;font-weight:800;width:15px;}}
  .dlg{{left:4px;right:4px;bottom:4px;height:24px;display:flex;align-items:center;}}
  .say{{font-size:8px;font-weight:700;line-height:1.1;}}
  .gear{{position:absolute;top:32px;right:4px;display:flex;flex-direction:column;gap:2px;z-index:3;}}
  .slot{{width:15px;height:15px;border:1px solid;border-radius:3px;background:#0b1430cc;
    display:flex;align-items:center;justify-content:center;}}
  .slot img{{width:13px;height:13px;}}
</style></head><body>
  <div class="screen">
    <div class="platform"></div>
    <img class="mascot" src="data:image/png;base64,{sprite}"/>
    <div class="gear">{gear}</div>
    <div class="box hp">
      <div class="row"><span class="nm">{name}</span><span class="lv">:L{level}</span></div>
      <div class="bar"><span class="tag">HP</span><div class="track"><div class="fill" style="width:{health}%;background:{hpcol}"></div></div></div>
      <div class="bar"><span class="tag x">XP</span><div class="track"><div class="fill" style="width:{xp}%;background:#3a7fd0"></div></div></div>
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
    mood = mood_override or mechanics.mood(state)
    nxt = mechanics.xp_to_next(state.level, cfg)
    health = int(max(0, min(100, state.health)))
    gear = "".join(
        f'<div class="slot" style="border-color:{_RARITY.get(r, "#b8c2cb")};'
        f'box-shadow:0 0 4px {_RARITY.get(r, "#b8c2cb")}">'
        f'<img src="data:image/png;base64,{_gear_icon_b64(slot)}"></div>'
        for slot, r in (equipped or {}).items()
        if os.path.exists(os.path.join(_SPRITES, "gear", slot + ".png")))
    html = _HTML.format(
        name=_html.escape(state.name), level=state.level,
        sprite=_sprite_b64(_sprite_for(state.stage, variant, mood)), gear=gear,
        health=health, hpcol=_hp_color(health),
        energy=int(max(0, state.energy)),
        food=int(max(0, min(100, 100 - state.hunger))),
        xp=int(max(0, min(100, state.xp / nxt * 100))) if nxt else 0,
        line=_html.escape(f'"{line}"') if line else "",
    )
    with open(path, "w") as f:
        f.write(html)
    return path
