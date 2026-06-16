"""Visual net-gun capture animation, authored at the Flipper One's native 256x144.

Same beat sequence as the ASCII version in ``animations`` — aim -> fire -> net ->
GOTCHA / got-away — but rendered as 256x144 frames the device can swap through
(Pwnagotchi-style "the image just changes"). All the art is real pixel-art
sprites (monster from ``view/monster_art``; the net-gun and energy net from
``sprites/fx/``) composited with CSS — no hand-drawn CSS shapes.

``render_sequence`` writes one HTML file per frame and returns their paths; the
docs pipeline screenshots them into the animated GIF shown in the README.
"""
from __future__ import annotations

import base64
import html as _html
import os

from . import encounter_screen, monster_art

_FX = os.path.join(os.path.dirname(__file__), "sprites", "fx")
_cache: dict = {}


def _fx_b64(name: str) -> str:
    if name not in _cache:
        with open(os.path.join(_FX, name + ".png"), "rb") as f:
            _cache[name] = base64.b64encode(f.read()).decode()
    return _cache[name]


# --- per-beat scene specs --------------------------------------------------
# gun:  inline style for the net-gun img (position + transform)
# proj: (left, top, size) for a net in flight, or None
# net:  (left, top, size, opacity) for the net over the monster, or None
# banner/mon/line as before.
_AIM = {"gun": "left:6px;bottom:18px;transform:rotate(-20deg)", "gunfx": "",
        "proj": None, "net": None, "banner": None, "mon": "none",
        "line": "{name} takes aim with the net-gun..."}
_FIRE = {"gun": "left:2px;bottom:16px;transform:rotate(-30deg)",
         "gunfx": "drop-shadow(0 0 5px #8ef)",
         "proj": (104, 58, 34), "net": None, "banner": None, "mon": "none",
         "line": "*fwoomp* -- net away!"}
_NET = {"gun": "left:6px;bottom:18px;transform:rotate(-20deg)", "gunfx": "",
        "proj": None, "net": (150, 6, 92, 1.0), "banner": None,
        "mon": "translateX(2px)", "line": "...will it hold?"}
_CAUGHT = {"gun": "left:6px;bottom:18px;transform:rotate(-20deg)", "gunfx": "",
           "proj": None, "net": (152, 8, 86, 1.0),
           "banner": ("GOTCHA!", "#58d858"), "mon": "scale(0.92)",
           "line": "{name}'s handshake was netted!"}
_AWAY = {"gun": "left:6px;bottom:18px;transform:rotate(-20deg)", "gunfx": "",
         "proj": None, "net": (150, 70, 78, 0.5),
         "banner": ("GOT AWAY!", "#e85040"), "mon": "translateY(-8px)",
         "mon_op": 0.25, "line": "{name} broke free -- no handshake."}

_SUCCESS = [_AIM, _FIRE, _NET, _CAUGHT]
_MISS = [_AIM, _FIRE, _NET, _AWAY]

_CSS = """
  html,body{margin:0;background:#000;}
  *{box-sizing:border-box;image-rendering:pixelated;}
  .screen{width:256px;height:144px;position:relative;overflow:hidden;
    font-family:'DejaVu Sans Mono',monospace;color:#283044;
    background:linear-gradient(#13213e 0%,#0d1730 55%,#0a1226 100%);}
  .platform{position:absolute;right:14px;top:64px;width:118px;height:22px;
    border-radius:50%;
    background:radial-gradient(closest-side,#1c5a6e 0%,#123a4a 70%,transparent 100%);}
  .mon{position:absolute;right:20px;top:6px;height:80px;z-index:1;
    filter:drop-shadow(0 2px 0 #0008);}
  .gun{position:absolute;height:42px;z-index:4;transform-origin:left bottom;
    filter:drop-shadow(0 1px 0 #0009);}
  .net{position:absolute;z-index:5;filter:drop-shadow(0 0 6px #8ef);}
  .proj{position:absolute;z-index:5;filter:drop-shadow(0 0 6px #8ef);}
  .streak{position:absolute;z-index:4;height:4px;width:46px;border-radius:2px;
    background:linear-gradient(90deg,transparent,#aef);}
  .banner{position:absolute;left:0;right:0;top:30px;text-align:center;z-index:6;
    font-size:26px;font-weight:800;letter-spacing:1px;
    text-shadow:0 2px 0 #0009,0 0 10px currentColor;}
  .box{position:absolute;background:#f6f1da;border:2px solid #39405a;border-radius:3px;
    box-shadow:inset 0 0 0 1px #ffffffcc;padding:2px 4px;z-index:7;}
  .dlg{left:4px;right:4px;bottom:4px;height:26px;display:flex;align-items:center;}
  .say{font-size:8px;font-weight:700;line-height:1.15;}
"""

_HTML = ("<!doctype html><html><head><meta charset='utf-8'><style>__CSS__"
         "</style></head><body><div class='screen'>"
         "<div class='platform'></div>"
         "<img class='mon' style='opacity:{mon_op};transform:{mon_tf}' "
         "src='data:image/png;base64,{sprite}'/>"
         "{net}{proj}"
         "<img class='gun' style='{gun};filter:{gunfx}' "
         "src='data:image/png;base64,{gun_b64}'/>"
         "{banner}"
         "<div class='box dlg'><span class='say'>{line}</span></div>"
         "</div></body></html>")


def _net_html(spec):
    if not spec:
        return ""
    left, top, size, op = spec
    return (f"<img class='net' style='left:{left}px;top:{top}px;width:{size}px;"
            f"opacity:{op}' src='data:image/png;base64,{_fx_b64('net')}'/>")


def _proj_html(spec):
    if not spec:
        return ""
    left, top, size = spec
    streak = (f"<div class='streak' style='left:{left - 40}px;"
              f"top:{top + size // 2 - 2}px'></div>")
    img = (f"<img class='proj' style='left:{left}px;top:{top}px;width:{size}px' "
           f"src='data:image/png;base64,{_fx_b64('net')}'/>")
    return streak + img


def _banner_html(spec):
    if not spec:
        return ""
    text, color = spec
    return f"<div class='banner' style='color:{color}'>{_html.escape(text)}</div>"


def _frame_html(sprite_b64: str, name: str, beat: dict) -> str:
    body = _HTML.format(
        sprite=sprite_b64, gun_b64=_fx_b64("netgun"),
        mon_op=beat.get("mon_op", 1.0), mon_tf=beat.get("mon", "none"),
        net=_net_html(beat.get("net")), proj=_proj_html(beat.get("proj")),
        gun=beat["gun"], gunfx=beat.get("gunfx") or "none",
        banner=_banner_html(beat.get("banner")),
        line=_html.escape(beat["line"].format(name=name, species=name)),
    )
    return body.replace("__CSS__", _CSS)


def beats(caught: bool = True) -> list:
    """The frame specs for a capture sequence (success or miss)."""
    return list(_SUCCESS if caught else _MISS)


def render_sequence(out_dir: str, monster: dict, caught: bool = True) -> list:
    """Write one HTML frame per beat into out_dir; return the frame paths.

    ``monster`` needs at least ``species`` (for the sprite) and ``name``.
    Unmodelled species fall back to the placeholder sprite."""
    out_dir = os.path.expanduser(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    species = str(monster.get("species", "Monster"))
    name = str(monster.get("name", species))
    sprite = monster_art.sprite_b64(species) or encounter_screen._fallback_b64()
    paths = []
    for i, beat in enumerate(beats(caught)):
        p = os.path.join(out_dir, f"capture_{i}.html")
        with open(p, "w") as f:
            f.write(_frame_html(sprite, name, beat))
        paths.append(p)
    return paths
