"""BLE battle render, 256x144 (grayscale device panel).

Renders the BLE attack as a short frame sequence -- one frame per technique
(SNIFF -> RE-PAIR -> BRUTE TK -> ... -> OWNED / CONTROL / IMMUNE) -- from the
``steps`` log a ``game.blebattle.battle_ble`` result carries. The pairing
security is shown as a badge; the final frame banners the outcome.
"""
from __future__ import annotations

import base64
import html as _html
import os

from . import monster_art

_SPRITES = os.path.join(os.path.dirname(__file__), "sprites")
_cache: dict = {}

_PAIRING_LABEL = {"just_works": "JUST WORKS", "pin": "6-DIGIT PIN",
                  "secure": "LE SECURE"}
# terminal step labels -> (banner, colour)
_OUTCOME = {"OWNED": ("OWNED!", "#7CFC00"), "IMMUNE": ("IMMUNE", "#7ddfff"),
            "FAILED": ("RESISTED", "#ff6a5a")}


def _fallback_b64() -> str:
    if "_fb" not in _cache:
        with open(os.path.join(_SPRITES, "adult.png"), "rb") as f:
            _cache["_fb"] = base64.b64encode(f.read()).decode()
    return _cache["_fb"]


def _player_b64(stem: str = "adult") -> str:
    key = ("p", stem)
    if key not in _cache:
        path = os.path.join(_SPRITES, stem + ".png")
        if not os.path.exists(path):
            path = os.path.join(_SPRITES, "adult.png")
        with open(path, "rb") as f:
            _cache[key] = base64.b64encode(f.read()).decode()
    return _cache[key]


_CSS = """
  html,body{margin:0;background:#000;}
  *{box-sizing:border-box;image-rendering:pixelated;}
  .screen{filter:grayscale(1);width:256px;height:144px;position:relative;overflow:hidden;
    font-family:'DejaVu Sans Mono',monospace;color:#eaf2ff;
    background:linear-gradient(#13213e 0%,#0d1730 55%,#0a1226 100%);}
  .platform{position:absolute;right:18px;top:62px;width:104px;height:20px;border-radius:50%;
    background:radial-gradient(closest-side,#1c5a6e 0%,#123a4a 70%,transparent 100%);}
  .mon{position:absolute;right:24px;top:10px;height:74px;z-index:1;
    filter:drop-shadow(0 2px 0 #0008);}
  .shark{position:absolute;left:-8px;bottom:18px;height:66px;z-index:2;
    filter:drop-shadow(0 2px 0 #0009);}
  .sig{position:absolute;left:52px;bottom:42px;width:40px;height:40px;z-index:1;
    border-radius:50%;border:3px solid #7ddfff66;
    box-shadow:0 0 0 6px #7ddfff22,0 0 0 12px #7ddfff11;opacity:.8;}
  .card{position:absolute;top:5px;left:5px;width:122px;background:#0b1430d8;
    border:1px solid #33405e;border-radius:3px;padding:2px 5px;z-index:3;}
  .card .t{font-size:8px;font-weight:800;color:#aee3ff;}
  .card .p{font-size:7px;font-weight:800;margin-top:1px;}
  .pill{background:#cfe;color:#10151f;border-radius:2px;padding:0 3px;}
  .step{position:absolute;top:34px;left:5px;width:130px;z-index:3;}
  .step .lbl{font-size:11px;font-weight:800;color:#ffd24a;letter-spacing:.5px;}
  .step .track{margin-top:3px;height:4px;background:#33405e;border-radius:2px;overflow:hidden;}
  .step .fill{height:100%;background:#7ddfff;}
  .banner{position:absolute;left:0;right:0;top:30px;text-align:center;z-index:5;
    font-size:26px;font-weight:800;letter-spacing:1px;color:#fff;transform:rotate(-4deg);
    text-shadow:-2px -2px 0 #102019,2px -2px 0 #102019,-2px 2px 0 #102019,
      2px 2px 0 #102019,0 0 12px currentColor;}
  .box{position:absolute;left:4px;right:4px;bottom:4px;height:26px;background:#f6f1da;
    border:2px solid #39405a;border-radius:3px;display:flex;align-items:center;
    padding:2px 4px;z-index:5;}
  .say{font-size:8px;font-weight:700;color:#283044;line-height:1.1;}
"""

# CSS injected past str.format via a __CSS__ marker (its { } would break format)
_DOC = ("<!doctype html><html><head><meta charset='utf-8'><style>__CSS__"
        "</style></head><body><div class='screen'>"
        "<div class='platform'></div><div class='sig'></div>"
        "<img class='mon' src='data:image/png;base64,{sprite}'/>"
        "<img class='shark' src='data:image/png;base64,{shark}'/>"
        "<div class='card'><div class='t'>BLE BATTLE</div>"
        "<div class='p'>pairing: <span class='pill'>{pairing}</span></div></div>"
        "{step}{banner}"
        "<div class='box'><span class='say'>{line}</span></div>"
        "</div></body></html>")


def _frame(sprite_b64, shark_b64, pairing, label, detail, frac, banner):
    step = ""
    if banner is None:
        step = (f"<div class='step'><div class='lbl'>{_html.escape(label)}</div>"
                f"<div class='track'><div class='fill' "
                f"style='width:{int(frac * 100)}%'></div></div></div>")
    bn = ""
    if banner is not None:
        text, col = banner
        bn = f"<div class='banner' style='color:{col}'>{_html.escape(text)}</div>"
    body = _DOC.format(sprite=sprite_b64, shark=shark_b64,
                       pairing=_html.escape(pairing),
                       step=step, banner=bn, line=_html.escape(detail)[:54])
    return body.replace("__CSS__", _CSS)


def render_sequence(out_dir: str, monster: dict, result: dict,
                    player: str = "adult") -> list:
    """Write one HTML frame per technique step; return the frame paths. ``player``
    is the shark sprite stem doing the hacking."""
    out_dir = os.path.expanduser(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    species = str(monster.get("species", "Monster"))
    pairing = _PAIRING_LABEL.get(str(monster.get("pairing", "")), "?")
    sprite = monster_art.sprite_b64(species) or _fallback_b64()
    shark = _player_b64(player or "adult")
    steps = (result or {}).get("steps") or [("RESULT", result.get("note", ""))]
    n = len(steps)
    paths = []
    for i, (label, detail) in enumerate(steps):
        banner = _OUTCOME.get(label)            # set only on the terminal step
        p = os.path.join(out_dir, f"blebattle_{i}.html")
        with open(p, "w") as f:
            f.write(_frame(sprite, shark, pairing, label, detail,
                           (i + 1) / n, banner))
        paths.append(p)
    return paths


def render(out_path: str, monster: dict, result: dict,
           player: str = "adult") -> str:
    """Single-frame convenience: the final outcome card. Returns out_path."""
    out_dir = os.path.dirname(os.path.expanduser(out_path)) or "."
    paths = render_sequence(out_dir, monster, result, player)
    last = paths[-1]
    path = os.path.expanduser(out_path)
    if last != path:
        os.replace(last, path)
    return path
