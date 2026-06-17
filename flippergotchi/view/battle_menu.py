"""The home "Battle Dojo" — its own section of the app, rendered at the Flipper
One's native 256x144.

Two screens:
  * the MENU      -- choose AUTO BATTLE (crack every captured target you haven't
                     battled yet) or MANUAL SELECT (scroll a list and pick one);
  * the TARGET LIST -- a scrollable list of captured "monsters" with a cursor.

Flipper One / FlipCTL button map (see ``BUTTONS``): from the home screen **OK**
opens the dojo; **Up/Down** move the cursor; **OK** confirms (run auto / battle
the highlighted target); **Back** closes the section.
"""
from __future__ import annotations

import base64
import html as _html
import os

_SPRITES = os.path.join(os.path.dirname(__file__), "sprites")
_cache: dict = {}

# Flipper One D-pad mapping for this section (documented + shown on screen).
BUTTONS = {
    "open": "OK",     # from the home screen: open the Battle Dojo
    "up": "Up",       # move cursor up
    "down": "Down",   # move cursor down
    "select": "OK",   # confirm: run auto / battle the highlighted target
    "back": "Back",   # close the section
}

# encryption -> tag colour (matches the bestiary / HUD palette)
_ENC_COLOR = {"open": "#b8c2cb", "wep": "#ffcf4d", "wpa": "#ffcf4d",
              "wpa2": "#c07bf0"}
_RARITY_COLOR = {"legendary": "#ffcf4d", "rare": "#5aa9ff", "epic": "#c07bf0",
                 "uncommon": "#7fd1a6"}


def _sprite_b64(name: str) -> str:
    if name not in _cache:
        path = os.path.join(_SPRITES, name + ".png")
        if not os.path.exists(path):
            path = os.path.join(_SPRITES, "adult.png")
        with open(path, "rb") as f:
            _cache[name] = base64.b64encode(f.read()).decode()
    return _cache[name]


_CSS = """
  html,body{margin:0;background:#000;}
  *{box-sizing:border-box;image-rendering:pixelated;}
  .screen{width:256px;height:144px;position:relative;overflow:hidden;
    font-family:'DejaVu Sans Mono',monospace;color:#eaf2ff;
    background:linear-gradient(#13213e 0%,#0d1730 55%,#0a1226 100%);}
  .title{position:absolute;top:5px;left:6px;right:6px;font-size:11px;
    font-weight:800;letter-spacing:.5px;color:#aee3ff;text-shadow:0 1px 0 #0009;}
  .title .sub{float:right;font-size:8px;color:#8fb0d8;font-weight:700;}
  .row{position:absolute;left:6px;right:6px;border:2px solid #39405a;
    border-radius:4px;background:#0d1c3aee;padding:4px 6px;}
  .row.sel{border-color:#ffd24a;background:#16294dee;
    box-shadow:0 0 6px #ffd24a99;}
  .cur{color:#ffd24a;font-weight:800;}
  .rt{font-size:10px;font-weight:800;}
  .rd{font-size:8px;color:#9fb4d8;margin-top:1px;}
  /* list rows */
  .lrow{position:absolute;left:6px;right:14px;height:18px;border-radius:3px;
    padding:1px 5px;display:flex;align-items:center;gap:5px;font-size:9px;
    font-weight:700;}
  .lrow.sel{background:#16294d;outline:2px solid #ffd24a;}
  .nm{flex:1;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;}
  .lv{color:#9fb4d8;font-size:8px;}
  .tag{font-size:7px;font-weight:800;color:#10151f;border-radius:2px;padding:0 3px;}
  .scroll{position:absolute;top:24px;bottom:22px;right:4px;width:4px;
    background:#1c2742;border-radius:2px;}
  .thumb{position:absolute;left:0;width:4px;background:#5a78b0;border-radius:2px;}
  .foot{position:absolute;left:0;right:0;bottom:0;height:18px;
    background:#0b1430;border-top:1px solid #2a3550;display:flex;
    align-items:center;justify-content:center;gap:10px;
    font-size:8px;font-weight:800;color:#9fb4d8;}
  .foot b{color:#ffd24a;}
  .shark{position:absolute;right:4px;bottom:20px;height:54px;opacity:.95;
    filter:drop-shadow(0 2px 0 #0009);}
  .empty{position:absolute;top:60px;left:0;right:0;text-align:center;
    font-size:9px;color:#9fb4d8;}
"""

_DOC = ("<!doctype html><html><head><meta charset='utf-8'><style>__CSS__"
        "</style></head><body><div class='screen'>{body}"
        "<div class='foot'>{foot}</div></div></body></html>")

_FOOT = ("<span><b>&#9650;&#9660;</b> Move</span>"
         "<span><b>OK</b> Select</span><span><b>Back</b> Exit</span>")


def _doc(body: str) -> str:
    return _DOC.format(body=body, foot=_FOOT).replace("__CSS__", _CSS)


def _write(out_path: str, html: str) -> str:
    path = os.path.expanduser(out_path)
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w") as f:
        f.write(html)
    return path


def render_menu(out_path: str, ready: int, cracked: int = 0, cursor: int = 0,
                player: str = "adult") -> str:
    """The dojo menu: AUTO vs MANUAL. ``ready`` = captured targets not yet
    battled; ``cursor`` 0=auto, 1=manual."""
    opts = [
        ("AUTO BATTLE", f"crack all {ready} fresh target(s)"),
        ("MANUAL SELECT", "scroll the list, pick a target"),
    ]
    rows = ""
    for i, (t, d) in enumerate(opts):
        sel = " sel" if i == cursor else ""
        cur = "&#9654; " if i == cursor else "&nbsp;&nbsp;"
        rows += (f"<div class='row{sel}' style='top:{34 + i * 40}px'>"
                 f"<div class='rt'><span class='cur'>{cur}</span>{t}</div>"
                 f"<div class='rd'>{_html.escape(d)}</div></div>")
    body = (f"<div class='title'>&#9876; BATTLE DOJO"
            f"<span class='sub'>{ready} ready &middot; {cracked} cracked</span></div>"
            f"{rows}"
            f"<img class='shark' src='data:image/png;base64,{_sprite_b64(player)}'/>")
    return _write(out_path, _doc(body))


def render_list(out_path: str, items: list, cursor: int = 0,
                window: int = 5) -> str:
    """The scrollable target list. ``items`` = dicts with name/level/encryption
    (+ optional rarity). ``cursor`` is the selected index."""
    n = len(items)
    if n == 0:
        body = ("<div class='title'>SELECT TARGET</div>"
                "<div class='empty'>No captured targets.<br>Go catch some "
                "monsters first!</div>")
        return _write(out_path, _doc(body))

    cursor = max(0, min(cursor, n - 1))
    top = max(0, min(cursor - window // 2, max(0, n - window)))
    visible = items[top:top + window]
    rows = ""
    for i, it in enumerate(visible):
        idx = top + i
        sel = " sel" if idx == cursor else ""
        cur = "&#9654;" if idx == cursor else "&nbsp;"
        enc = str(it.get("encryption", "") or "").lower()
        rarity = str(it.get("rarity", "") or "")
        tagtxt = rarity.upper() if rarity in _RARITY_COLOR else enc.upper()
        tagcol = _RARITY_COLOR.get(rarity) or _ENC_COLOR.get(enc, "#9fb0c4")
        rows += (
            f"<div class='lrow{sel}' style='top:{24 + i * 19}px'>"
            f"<span class='cur'>{cur}</span>"
            f"<span class='nm'>{_html.escape(str(it.get('name', '?'))[:18])}</span>"
            f"<span class='lv'>L{it.get('level', 1)}</span>"
            f"<span class='tag' style='background:{tagcol}'>{_html.escape(tagtxt)}</span>"
            f"</div>")
    # scrollbar thumb
    track_h = 144 - 24 - 22
    thumb_h = max(8, int(track_h * window / n))
    thumb_y = int(track_h * top / n)
    scroll = (f"<div class='scroll'><div class='thumb' "
              f"style='top:{thumb_y}px;height:{thumb_h}px'></div></div>")
    body = (f"<div class='title'>SELECT TARGET"
            f"<span class='sub'>{cursor + 1}/{n}</span></div>{rows}{scroll}")
    return _write(out_path, _doc(body))
