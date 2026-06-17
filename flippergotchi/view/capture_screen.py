"""Visual net-gun capture animation, authored at the Flipper One's native 256x144.

The capture mirrors the real pentest flow (see ``core/wifi/capture.py``): lock the
target, fire deauth frames to kick clients, then listen for the WPA 4-way
handshake until ``cfg.capture_timeout`` elapses. The shark fires a net-gun from
the lower-left and the net lands on the wild monster's head; a small status HUD
shows the deauth / capture activity running in the background. Two outcomes:

  * handshake captured  -> "GOTCHA!"  (the M1-M4 exchange was netted)
  * timed out, none seen -> "NO HANDSHAKE" (the AP never coughed one up)

All art is real pixel-art sprites (player + monster; net-gun + energy net from
``sprites/fx/``) composited with CSS. ``render_sequence`` writes one HTML file
per frame; the docs pipeline screenshots them into the README GIFs.
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


# sparkle positions (left,top,size) around the win banner
_SPARKS = [(96, 20, 14), (150, 18, 11), (118, 56, 12), (164, 48, 14), (84, 44, 10)]
_GUN = "left:70px;bottom:30px;transform:rotate(-30deg)"
_GUN_FIRE = "left:66px;bottom:27px;transform:rotate(-40deg)"


def _beats(caught: bool, timeout: int, deauth: int) -> list:
    """Build the four frame specs, parameterised by the live capture settings.

    status: (text, colour); bar: capture-progress fraction or None;
    net/proj/banner as positioned elements."""
    lock = {"gun": _GUN, "gunfx": "", "proj": None, "net": None, "banner": None,
            "mon": "none", "status": ("TARGET LOCKED", "#7ddfff"), "bar": None,
            "line": "{name} -- locking on with the net-gun..."}
    deauth_beat = {
        "gun": _GUN_FIRE, "gunfx": "drop-shadow(0 0 5px #8ef)",
        "proj": (100, 46, 28), "net": None, "banner": None, "mon": "none",
        "status": (f"DEAUTH x{deauth}", "#ff6a5a"), "bar": None,
        "line": "*fwoomp* deauth -- kicking clients to force a handshake!"}
    capture = {
        "gun": _GUN, "gunfx": "", "proj": None, "net": (94, 24, 64, 1.0),
        "banner": None, "mon": "translateX(2px)",
        "status": (f"CAPTURE EAPOL  ~{timeout}s", "#ffd24a"), "bar": 0.6,
        "line": "listening for the WPA 4-way handshake..."}
    won = {"gun": _GUN, "gunfx": "", "proj": None, "net": (96, 26, 60, 1.0),
           "banner": ("GOTCHA!", "#7CFC00", "win"), "mon": "scale(0.94)",
           "status": ("HANDSHAKE OK  M1-M4", "#7CFC00"), "bar": 1.0,
           "line": "{name}'s 4-way handshake was captured!"}
    failed = {"gun": _GUN, "gunfx": "", "proj": None, "net": (88, 62, 58, 0.4),
              "banner": ("NO HANDSHAKE", "#ffb02e", "fail"), "mon": "none",
              "status": (f"NO HANDSHAKE  {timeout}s", "#ff6a5a"), "bar": 1.0,
              "line": "timed out after {t}s -- no client reconnected, no handshake."}
    return [lock, deauth_beat, capture, won if caught else failed]


_CSS = """
  html,body{margin:0;background:#000;}
  *{box-sizing:border-box;image-rendering:pixelated;}
  .screen{filter:grayscale(1);width:256px;height:144px;position:relative;overflow:hidden;
    font-family:'DejaVu Sans Mono',monospace;color:#283044;
    background:linear-gradient(#13213e 0%,#0d1730 55%,#0a1226 100%);}
  .platform{position:absolute;right:14px;top:64px;width:118px;height:22px;
    border-radius:50%;
    background:radial-gradient(closest-side,#1c5a6e 0%,#123a4a 70%,transparent 100%);}
  .mon{position:absolute;right:8px;top:16px;height:78px;max-width:128px;z-index:1;
    filter:drop-shadow(0 2px 0 #0008);}
  .shark{position:absolute;left:-8px;bottom:26px;height:80px;z-index:4;
    filter:drop-shadow(0 2px 0 #0009);}
  .gun{position:absolute;height:34px;z-index:6;transform-origin:left bottom;
    filter:drop-shadow(0 1px 0 #0009);}
  .net{position:absolute;z-index:5;filter:drop-shadow(0 0 6px #8ef);}
  .proj{position:absolute;z-index:5;filter:drop-shadow(0 0 6px #8ef);}
  .streak{position:absolute;z-index:4;height:4px;width:42px;border-radius:2px;
    background:linear-gradient(90deg,transparent,#aef);}
  /* background-activity HUD: deauth / capture status + progress */
  .hud{position:absolute;top:5px;left:5px;z-index:7;background:#0b1430d8;
    border:1px solid #33405e;border-radius:3px;padding:2px 5px;min-width:96px;}
  .hud .t{font-size:7px;font-weight:800;letter-spacing:.3px;display:block;}
  .hud .track{margin-top:2px;height:3px;background:#33405e;border-radius:2px;
    overflow:hidden;}
  .hud .fill{height:100%;}
  .banner{position:absolute;left:0;right:0;top:24px;text-align:center;z-index:8;
    font-size:28px;font-weight:800;letter-spacing:2px;color:#fff;
    transform:rotate(-5deg);
    text-shadow:-2px -2px 0 #102019,2px -2px 0 #102019,-2px 2px 0 #102019,
      2px 2px 0 #102019,0 0 12px currentColor,0 3px 0 #0008;}
  .banner.fail{transform:rotate(2deg);font-size:24px;
    text-shadow:-2px -2px 0 #2a1a06,2px -2px 0 #2a1a06,-2px 2px 0 #2a1a06,
      2px 2px 0 #2a1a06,0 0 12px currentColor;}
  .spk{position:absolute;z-index:8;color:#ffe79a;font-size:13px;
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
         "{hud}{banner}"
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
    streak = (f"<div class='streak' style='left:{left - 36}px;"
              f"top:{top + size // 2 - 2}px'></div>")
    img = (f"<img class='proj' style='left:{left}px;top:{top}px;width:{size}px' "
           f"src='data:image/png;base64,{_fx_b64('net')}'/>")
    return streak + img


def _hud_html(status, bar):
    text, color = status
    out = (f"<div class='hud'><span class='t' style='color:{color}'>"
           f"{_html.escape(text)}</span>")
    if bar is not None:
        pct = int(max(0, min(1.0, bar)) * 100)
        out += (f"<div class='track'><div class='fill' "
                f"style='width:{pct}%;background:{color}'></div></div>")
    return out + "</div>"


def _banner_html(spec):
    if not spec:
        return ""
    text, color, kind = spec
    out = ""
    if kind == "win":
        for x, y, s in _SPARKS:
            out += (f"<span class='spk' style='left:{x}px;top:{y}px;"
                    f"font-size:{s}px'>&#10022;</span>")
    out += (f"<div class='banner {kind}' style='color:{color}'>"
            f"{_html.escape(text)}</div>")
    return out


def _frame_html(sprite_b64: str, shark_b64: str, name: str, timeout: int,
                beat: dict) -> str:
    body = _HTML.format(
        sprite=sprite_b64, shark=shark_b64, gun_b64=_fx_b64("netgun"),
        mon_op=beat.get("mon_op", 1.0), mon_tf=beat.get("mon", "none"),
        net=_net_html(beat.get("net")), proj=_proj_html(beat.get("proj")),
        gun=beat["gun"], gunfx=beat.get("gunfx") or "none",
        hud=_hud_html(beat["status"], beat.get("bar")),
        banner=_banner_html(beat.get("banner")),
        line=_html.escape(beat["line"].format(name=name, species=name, t=timeout)),
    )
    return body.replace("__CSS__", _CSS)


def beats(caught: bool = True, timeout: int = 20, deauth: int = 5) -> list:
    """The frame specs for a capture sequence (success or no-handshake)."""
    return _beats(caught, int(timeout), int(deauth))


def render_sequence(out_dir: str, monster: dict, caught: bool = True,
                    player: str = "adult", timeout: int = 20,
                    deauth: int = 5) -> list:
    """Write one HTML frame per beat into out_dir; return the frame paths.

    ``monster`` needs at least ``species`` (sprite) and ``name``. ``player`` is
    the shark sprite stem; ``timeout`` (s) and ``deauth`` (frame count) are the
    live capture settings shown in the status HUD. ``caught=False`` renders the
    timed-out "NO HANDSHAKE" outcome."""
    out_dir = os.path.expanduser(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    species = str(monster.get("species", "Monster"))
    name = str(monster.get("name", species))
    sprite = monster_art.sprite_b64(species) or _player_b64("adult")
    shark = _player_b64(player or "adult")
    paths = []
    for i, beat in enumerate(beats(caught, timeout, deauth)):
        p = os.path.join(out_dir, f"capture_{i}.html")
        with open(p, "w") as f:
            f.write(_frame_html(sprite, shark, name, int(timeout), beat))
        paths.append(p)
    return paths
