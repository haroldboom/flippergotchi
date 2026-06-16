"""Visual net-gun capture animation, authored at the Flipper One's native 256x144.

The capture is the same beat sequence as the ASCII version in ``animations`` —
aim -> fire -> net -> GOTCHA / got-away — but rendered as 256x144 frames the
device can swap through (Pwnagotchi-style "the image just changes"). The monster
art comes from ``view/monster_art``; the net-gun, net mesh and banner are CSS.

``render_sequence`` writes one HTML file per frame and returns their paths; the
docs pipeline screenshots them into the animated GIF shown in the README.
"""
from __future__ import annotations

import html as _html
import os

from . import encounter_screen, monster_art

# --- per-beat scene specs --------------------------------------------------
# Each beat positions the net-gun, an optional in-flight projectile, an optional
# net mesh over the monster, an optional centre banner, the monster's own
# transform, and the dialogue line. {name}/{species} are filled per monster.
_AIM = {"gun": "left:10px;bottom:24px;transform:rotate(0deg)",
        "muzzle": 0.5, "proj": None, "net": None, "banner": None,
        "mon": "none", "line": "{name} takes aim with the net-gun..."}
_FIRE = {"gun": "left:4px;bottom:22px;transform:rotate(-12deg)",
         "muzzle": 1.0, "proj": (118, 66, 1.0), "net": None, "banner": None,
         "mon": "none", "line": "*fwoomp* -- net away!"}
_NET = {"gun": "left:10px;bottom:24px;transform:rotate(0deg)",
        "muzzle": 0.2, "proj": None, "net": (146, 4, 92, 1.0, ""),
        "banner": None, "mon": "translateX(2px)", "line": "...will it hold?"}
_CAUGHT = {"gun": "left:10px;bottom:24px;transform:rotate(0deg)",
           "muzzle": 0.0, "proj": None, "net": (148, 6, 88, 1.0, "tight"),
           "banner": ("GOTCHA!", "#58d858"), "mon": "scale(0.92)",
           "line": "{name}'s handshake was netted!"}
_AWAY = {"gun": "left:10px;bottom:24px;transform:rotate(0deg)",
         "muzzle": 0.0, "proj": None, "net": (150, 64, 78, 0.45, "drop"),
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
  /* net-gun (CSS): dark body + angled barrel + glowing muzzle */
  .gun{position:absolute;width:48px;height:28px;z-index:4;}
  .gun .body{position:absolute;left:0;bottom:0;width:34px;height:18px;
    background:linear-gradient(#39405a,#222838);border:2px solid #5a6480;
    border-radius:5px;}
  .gun .barrel{position:absolute;left:22px;bottom:9px;width:26px;height:8px;
    background:linear-gradient(#4a5270,#2a3045);border:1px solid #6a76a0;
    border-radius:3px;transform-origin:left center;transform:rotate(-32deg);}
  .gun .muzzle{position:absolute;right:-3px;top:-1px;width:8px;height:8px;
    border-radius:50%;background:#7df;box-shadow:0 0 6px #8ef,0 0 12px #4cf;}
  /* net mesh over the monster */
  .net{position:absolute;border-radius:50%;border:3px solid #e6f7ff;z-index:5;
    background:
      repeating-linear-gradient(45deg,#bfe8ff66 0 2px,transparent 2px 8px),
      repeating-linear-gradient(-45deg,#bfe8ff66 0 2px,transparent 2px 8px);
    box-shadow:0 0 8px #8ef,inset 0 0 9px #8ef7;}
  .net.tight{box-shadow:0 0 12px #aff,inset 0 0 12px #8efb;}
  /* in-flight projectile: a bright netball + a motion streak */
  .proj{position:absolute;width:26px;height:26px;border-radius:50%;z-index:5;
    border:3px solid #eaffff;
    background:repeating-linear-gradient(45deg,#bfe8ff99 0 2px,transparent 2px 6px);
    box-shadow:0 0 10px #8ef,0 0 18px #4cf;}
  .proj::before{content:'';position:absolute;right:20px;top:11px;width:40px;height:4px;
    background:linear-gradient(90deg,transparent,#aef);border-radius:2px;}
  .banner{position:absolute;left:0;right:0;top:30px;text-align:center;z-index:6;
    font-size:26px;font-weight:800;letter-spacing:1px;
    text-shadow:0 2px 0 #0009,0 0 10px currentColor;}
  .box{position:absolute;background:#f6f1da;border:2px solid #39405a;border-radius:3px;
    box-shadow:inset 0 0 0 1px #ffffffcc;padding:2px 4px;z-index:7;}
  .dlg{left:4px;right:4px;bottom:4px;height:26px;display:flex;align-items:center;}
  .say{font-size:8px;font-weight:700;line-height:1.15;}
"""

# NOTE: the CSS (with its literal { }) is injected via a __CSS__ marker AFTER
# str.format runs, so format only ever sees the intended placeholders.
_HTML = ("<!doctype html><html><head><meta charset='utf-8'><style>__CSS__"
         "</style></head><body><div class='screen'>"
         "<div class='platform'></div>"
         "<img class='mon' style='opacity:{mon_op};transform:{mon_tf}' "
         "src='data:image/png;base64,{sprite}'/>"
         "{net}{proj}"
         "<div class='gun' style='{gun}'><div class='body'></div>"
         "<div class='barrel'></div><div class='muzzle' style='opacity:{muzzle}'></div></div>"
         "{banner}"
         "<div class='box dlg'><span class='say'>{line}</span></div>"
         "</div></body></html>")


def _net_html(spec):
    if not spec:
        return ""
    left, top, size, op, cls = spec
    return (f"<div class='net {cls}' style='left:{left}px;top:{top}px;"
            f"width:{size}px;height:{size}px;opacity:{op}'></div>")


def _proj_html(spec):
    if not spec:
        return ""
    left, top, _ = spec
    return f"<div class='proj' style='left:{left}px;top:{top}px'></div>"


def _banner_html(spec):
    if not spec:
        return ""
    text, color = spec
    return f"<div class='banner' style='color:{color}'>{_html.escape(text)}</div>"


def _frame_html(sprite_b64: str, name: str, beat: dict) -> str:
    body = _HTML.format(
        sprite=sprite_b64,
        mon_op=beat.get("mon_op", 1.0), mon_tf=beat.get("mon", "none"),
        net=_net_html(beat.get("net")), proj=_proj_html(beat.get("proj")),
        gun=beat["gun"], muzzle=beat["muzzle"],
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
