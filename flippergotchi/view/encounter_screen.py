"""Visual WiFi/BLE encounter card, authored at the Flipper One's native 256x144.

A classic "A wild <species> appeared!" screen: the monster stands on a
platform upper-right with its stat card upper-left (species / level / encryption
/ crack-difficulty), and a cream dialogue box plus a Capture/Run menu run along
the bottom. The monster art comes from ``view/monster_art`` (the AP-species
villains and the BLE mini-monsters); anything unmodelled falls back to a "?".

Scaled up nearest-neighbour by the caller (same pipeline as flipctl/battle_screen).
"""
from __future__ import annotations

import base64
import html as _html
import os

from . import monster_art

_SPRITES = os.path.join(os.path.dirname(__file__), "sprites")
_cache: dict = {}

# encryption -> tag colour (mirrors the bestiary showcase / HUD rarity palette)
_ENC_COLOR = {"open": "#b8c2cb", "wep": "#7fd1a6", "wpa": "#5aa9ff",
              "wpa2": "#c07bf0"}


def _fallback_b64() -> str:
    if "_fallback" not in _cache:
        path = os.path.join(_SPRITES, "adult.png")
        with open(path, "rb") as f:
            _cache["_fallback"] = base64.b64encode(f.read()).decode()
    return _cache["_fallback"]


def _diff_color(pct: float) -> str:
    return "#58d858" if pct < 34 else "#f0c020" if pct < 67 else "#e85040"


_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>wild {species}</title><style>
  html,body{{margin:0;background:#000;}}
  *{{box-sizing:border-box;image-rendering:pixelated;}}
  .screen{{filter:grayscale(1);image-rendering:pixelated;width:256px;height:144px;position:relative;overflow:hidden;
    font-family:'DejaVu Sans Mono',monospace;color:#283044;
    background:linear-gradient(#13213e 0%,#0d1730 55%,#0a1226 100%);}}
  .platform{{position:absolute;right:14px;top:64px;width:118px;height:22px;
    border-radius:50%;
    background:radial-gradient(closest-side,#1c5a6e 0%,#123a4a 70%,transparent 100%);}}
  .mon{{position:absolute;right:8px;top:16px;height:78px;max-width:128px;z-index:1;
    filter:drop-shadow(0 2px 0 #0008);}}
  .box{{position:absolute;background:#f6f1da;border:2px solid #39405a;border-radius:3px;
    box-shadow:inset 0 0 0 1px #ffffffcc;padding:2px 4px;z-index:3;}}
  .card{{top:6px;left:4px;width:106px;}}
  .row{{display:flex;justify-content:space-between;align-items:center;gap:3px;}}
  .nm{{font-size:9px;font-weight:800;letter-spacing:.3px;}}
  .lv{{font-size:8px;font-weight:800;}}
  .sub{{font-size:7px;font-weight:700;color:#5a6072;margin-top:1px;}}
  .bar{{display:flex;align-items:center;gap:2px;margin-top:2px;}}
  .tag{{font-size:6px;font-weight:800;color:#1a1f2c;border-radius:2px;padding:0 3px;}}
  .lbl{{font-size:6px;font-weight:800;color:#5a6072;}}
  .track{{flex:1;height:5px;background:#5a6072;border:1px solid #2a3045;border-radius:2px;overflow:hidden;}}
  .fill{{height:100%;}}
  .dlg{{left:4px;bottom:4px;width:168px;height:40px;display:flex;align-items:center;}}
  .say{{font-size:8px;font-weight:700;line-height:1.15;}}
  .menu{{right:4px;bottom:4px;width:76px;height:40px;}}
  .opt{{font-size:8px;font-weight:800;line-height:1.4;}}
  .opt b{{color:#c2402a;}}
</style></head><body>
  <div class="screen">
    <div class="platform"></div>
    <img class="mon" src="data:image/png;base64,{sprite}"/>
    <div class="box card">
      <div class="row"><span class="nm">{species}</span><span class="lv">:L{level}</span></div>
      <div class="sub">{name}</div>
      <div class="bar"><span class="tag" style="background:{enccol}">{enc}</span>
        <span class="lbl">DEF</span>
        <div class="track"><div class="fill" style="width:{defpct}%;background:{defcol}"></div></div>
      </div>
    </div>
    <div class="box dlg"><span class="say">{line}</span></div>
    <div class="box menu"><div class="opt"><b>&#9654;A</b> CAPTURE<br>&nbsp;&nbsp;B&nbsp; RUN</div></div>
  </div>
</body></html>"""


def render(out_path: str, monster: dict, line: str = "") -> str:
    """Write a 256x144 encounter card for ``monster`` (a dict with species/name/
    level/encryption/defense). ``line`` overrides the default appear message.
    Returns out_path."""
    path = os.path.expanduser(out_path)
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)

    species = str(monster.get("species", "Monster"))
    enc = str(monster.get("encryption", "") or "").lower()
    kind = str(monster.get("kind", "wifi"))
    tag = enc.upper() if enc else ("BLE" if kind == "ble" else "OPEN")
    defense = int(max(0, min(100, monster.get("defense", 0) or 0)))
    sprite = monster_art.sprite_b64(species) or _fallback_b64()
    msg = line or f"A wild {species} appeared!"

    html = _HTML.format(
        species=_html.escape(species), level=monster.get("level", 1),
        name=_html.escape(str(monster.get("name", ""))[:20]),
        enc=_html.escape(tag), enccol=_ENC_COLOR.get(enc, "#9fb0c4"),
        defpct=defense, defcol=_diff_color(defense),
        sprite=sprite, line=_html.escape(msg),
    )
    with open(path, "w") as f:
        f.write(html)
    return path
