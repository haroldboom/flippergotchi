"""Visual net-gun capture animation, authored at the Flipper One's native 256x144.

Same beat sequence as the ASCII version in ``animations`` — aim -> fire -> net ->
GOTCHA / got-away — rendered as 256x144 frames the device swaps through
(Pwnagotchi-style "the image just changes"). The player shark fires a net-gun
from the lower-left and the net lands on the wild monster's head. All art is real
pixel-art sprites (player + monster from sprites; net-gun + energy net from
``sprites/fx/``) composited with CSS.

``render_sequence`` writes one HTML file per frame and returns their paths; the
docs pipeline screenshots them into the animated GIF shown in the README.
"""
from __future__ import annotations

import base64
import html as _html
import os

from . import monster_art

_SPRITES = os.path.join(os.path.dirname(__file__), "sprites")
_FX = os.path.join(_SPRITES, "fx")
_cache: dict = {}


def _fx_b64(name: str) -> str:
    if ("fx", name) not in _cache:
        with open(os.path.join(_FX, name + ".png"), "rb") as f:
            _cache[("fx", name)] = base64.b64encode(f.read()).decode()
    return _cache[("fx", name)]


def _player_b64(stem: str = "adult") -> str:
    if ("p", stem) not in _cache:
        path = os.path.join(_SPRITES, stem + ".png")
        if not os.path.exists(path):
            path = os.path.join(_SPRITES, "adult.png")
        with open(path, "rb") as f:
            _cache[("p", stem)] = base64.b64encode(f.read()).decode()
    return _cache[("p", stem)]


# --- per-beat scene specs --------------------------------------------------
# gun:  inline style for the net-gun img (position + transform)
# proj: (left, top, size) for a net in flight, or None
# net:  (left, top, size, opacity) for the net over the monster's HEAD, or None
# banner: (text, colour, kind) where kind is "win" | "lose", or None
_AIM = {"gun": "left:70px;bottom:30px;transform:rotate(-30deg)", "gunfx": "",
        "proj": None, "net": None, "banner": None, "mon": "none",
        "line": "{name} takes aim with the net-gun..."}
_FIRE = {"gun": "left:66px;bottom:27px;transform:rotate(-40deg)",
         "gunfx": "drop-shadow(0 0 5px #8ef)",
         "proj": (104, 44, 30), "net": None, "banner": None, "mon": "none",
         "line": "*fwoomp* -- net away!"}
_NET = {"gun": "left:70px;bottom:30px;transform:rotate(-30deg)", "gunfx": "",
        "proj": None, "net": (90, 8, 70, 1.0), "banner": None,
        "mon": "translateX(2px)", "line": "...will it hold?"}
_CAUGHT = {"gun": "left:70px;bottom:30px;transform:rotate(-30deg)", "gunfx": "",
           "proj": None, "net": (92, 10, 66, 1.0),
           "banner": ("GOTCHA!", "#7CFC00", "win"), "mon": "scale(0.94)",
           "line": "{name}'s handshake was netted!"}
_AWAY = {"gun": "left:70px;bottom:30px;transform:rotate(-30deg)", "gunfx": "",
         "proj": None, "net": (86, 60, 66, 0.5),
         "banner": ("GOT AWAY!", "#ff5a44", "lose"), "mon": "translateY(-9px)",
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
  .shark{position:absolute;left:-8px;bottom:26px;height:80px;z-index:4;
    filter:drop-shadow(0 2px 0 #0009);}
  .gun{position:absolute;height:34px;z-index:6;transform-origin:left bottom;
    filter:drop-shadow(0 1px 0 #0009);}
  .net{position:absolute;z-index:5;filter:drop-shadow(0 0 6px #8ef);}
  .proj{position:absolute;z-index:5;filter:drop-shadow(0 0 6px #8ef);}
  .streak{position:absolute;z-index:4;height:4px;width:42px;border-radius:2px;
    background:linear-gradient(90deg,transparent,#aef);}
  /* arcade GOTCHA banner: gold flash + thick-outlined word + sparkles */
  .flash{position:absolute;left:90px;top:42px;width:150px;height:90px;z-index:5;
    transform:translate(-50%,-50%);
    background:radial-gradient(closest-side,#ffe79a88 0%,#ffd24a33 45%,transparent 70%);}
  .banner{position:absolute;left:0;right:0;top:24px;text-align:center;z-index:7;
    font-size:30px;font-weight:800;letter-spacing:2px;color:#fff;
    transform:rotate(-5deg);
    text-shadow:-2px -2px 0 #102019,2px -2px 0 #102019,-2px 2px 0 #102019,
      2px 2px 0 #102019,0 0 12px currentColor,0 3px 0 #0008;}
  .banner.lose{transform:rotate(2deg);
    text-shadow:-2px -2px 0 #2a0f0c,2px -2px 0 #2a0f0c,-2px 2px 0 #2a0f0c,
      2px 2px 0 #2a0f0c,0 0 12px currentColor;}
  .spk{position:absolute;z-index:7;color:#ffe79a;font-size:13px;
    text-shadow:0 0 6px #ffd24a;}
  .box{position:absolute;background:#f6f1da;border:2px solid #39405a;border-radius:3px;
    box-shadow:inset 0 0 0 1px #ffffffcc;padding:2px 4px;z-index:8;}
  .dlg{left:4px;right:4px;bottom:4px;height:26px;display:flex;align-items:center;}
  .say{font-size:8px;font-weight:700;line-height:1.15;}
"""

_HTML = ("<!doctype html><html><head><meta charset='utf-8'><style>__CSS__"
         "</style></head><body><div class='screen'>"
         "<div class='platform'></div>"
         "<img class='mon' style='opacity:{mon_op};transform:{mon_tf}' "
         "src='data:image/png;base64,{sprite}'/>"
         "{net}{proj}"
         "<img class='shark' src='data:image/png;base64,{shark}'/>"
         "<img class='gun' style='{gun};filter:{gunfx}' "
         "src='data:image/png;base64,{gun_b64}'/>"
         "{banner}"
         "<div class='box dlg'><span class='say'>{line}</span></div>"
         "</div></body></html>")

# sparkle positions (left,top,size) around the win banner
_SPARKS = [(96, 20, 14), (150, 18, 11), (118, 56, 12), (164, 48, 14), (84, 44, 10)]


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
    streak = (f"<div class='streak' style='left:{left - 36}px;"
              f"top:{top + size // 2 - 2}px'></div>")
    img = (f"<img class='proj' style='left:{left}px;top:{top}px;width:{size}px' "
           f"src='data:image/png;base64,{_fx_b64('net')}'/>")
    return streak + img


def _banner_html(spec):
    if not spec:
        return ""
    text, color, kind = spec
    out = ""
    if kind == "win":
        out += "<div class='flash'></div>"
        for x, y, s in _SPARKS:
            out += (f"<span class='spk' style='left:{x}px;top:{y}px;"
                    f"font-size:{s}px'>&#10022;</span>")
    out += (f"<div class='banner {kind}' style='color:{color}'>"
            f"{_html.escape(text)}</div>")
    return out


def _frame_html(sprite_b64: str, shark_b64: str, name: str, beat: dict) -> str:
    body = _HTML.format(
        sprite=sprite_b64, shark=shark_b64, gun_b64=_fx_b64("netgun"),
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


def render_sequence(out_dir: str, monster: dict, caught: bool = True,
                    player: str = "adult") -> list:
    """Write one HTML frame per beat into out_dir; return the frame paths.

    ``monster`` needs at least ``species`` (sprite) and ``name``. ``player`` is
    the shark sprite stem doing the capturing (e.g. "adult", "blue-adult").
    Unmodelled species fall back to the placeholder sprite."""
    out_dir = os.path.expanduser(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    species = str(monster.get("species", "Monster"))
    name = str(monster.get("name", species))
    sprite = monster_art.sprite_b64(species) or _player_b64("adult")
    shark = _player_b64(player or "adult")
    paths = []
    for i, beat in enumerate(beats(caught)):
        p = os.path.join(out_dir, f"capture_{i}.html")
        with open(p, "w") as f:
            f.write(_frame_html(sprite, shark, name, beat))
        paths.append(p)
    return paths
