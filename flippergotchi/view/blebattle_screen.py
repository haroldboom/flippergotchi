"""BLE battle outcome card, 256x144 (grayscale device panel).

Shows the result of battling a Bluetooth mini-monster: cracking its pairing
(crackle) to recover the LTK, taking control via a GATT write, or hitting an
immune LE-Secure-Connections device. The pairing security is the monster's
"defense" and is shown as a badge.
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


def _fallback_b64() -> str:
    if "_fb" not in _cache:
        with open(os.path.join(_SPRITES, "adult.png"), "rb") as f:
            _cache["_fb"] = base64.b64encode(f.read()).decode()
    return _cache["_fb"]


_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
  html,body{{margin:0;background:#000;}}
  *{{box-sizing:border-box;image-rendering:pixelated;}}
  .screen{{filter:grayscale(1);width:256px;height:144px;position:relative;overflow:hidden;
    font-family:'DejaVu Sans Mono',monospace;color:#eaf2ff;
    background:linear-gradient(#13213e 0%,#0d1730 55%,#0a1226 100%);}}
  .platform{{position:absolute;right:18px;top:62px;width:104px;height:20px;border-radius:50%;
    background:radial-gradient(closest-side,#1c5a6e 0%,#123a4a 70%,transparent 100%);}}
  .mon{{position:absolute;right:30px;top:10px;height:74px;z-index:1;
    filter:drop-shadow(0 2px 0 #0008);}}
  /* concentric BLE "signal" rings, lower-left */
  .sig{{position:absolute;left:18px;bottom:34px;width:54px;height:54px;z-index:1;
    border-radius:50%;border:3px solid #7ddfff66;
    box-shadow:0 0 0 7px #7ddfff22,0 0 0 14px #7ddfff11;opacity:.8;}}
  .card{{position:absolute;top:5px;left:5px;width:120px;background:#0b1430d8;
    border:1px solid #33405e;border-radius:3px;padding:2px 5px;z-index:3;}}
  .card .t{{font-size:9px;font-weight:800;color:#aee3ff;}}
  .card .p{{font-size:7px;font-weight:800;margin-top:2px;}}
  .pill{{background:#cfe;color:#10151f;border-radius:2px;padding:0 3px;}}
  .banner{{position:absolute;left:0;right:0;top:30px;text-align:center;z-index:5;
    font-size:26px;font-weight:800;letter-spacing:1px;color:#fff;transform:rotate(-4deg);
    text-shadow:-2px -2px 0 #102019,2px -2px 0 #102019,-2px 2px 0 #102019,
      2px 2px 0 #102019,0 0 12px currentColor;}}
  .box{{position:absolute;left:4px;right:4px;bottom:4px;height:26px;background:#f6f1da;
    border:2px solid #39405a;border-radius:3px;display:flex;align-items:center;
    padding:2px 4px;z-index:5;}}
  .say{{font-size:8px;font-weight:700;color:#283044;line-height:1.1;}}
</style></head><body><div class="screen">
  <div class="platform"></div>
  <div class="sig"></div>
  <img class="mon" src="data:image/png;base64,{sprite}"/>
  <div class="card"><div class="t">BLE BATTLE</div>
    <div class="p">pairing: <span class="pill">{pairing}</span></div></div>
  <div class="banner" style="color:{bcol}">{banner}</div>
  <div class="box"><span class="say">{line}</span></div>
</div></body></html>"""


def _outcome(result: dict):
    """(banner, colour) for a battle result dict."""
    r = (result or {}).get("result", "")
    via = (result or {}).get("via", "")
    if r == "cracked":
        return ("OWNED!", "#7CFC00") if "crackle" in via else ("CONTROL!", "#7CFC00")
    if r == "immune":
        return "IMMUNE", "#7ddfff"
    return "RESISTED", "#ff6a5a"


def render(out_path: str, monster: dict, result: dict) -> str:
    """Write a BLE battle outcome card. ``monster`` has species/name/level/
    pairing; ``result`` is a battle() result dict."""
    path = os.path.expanduser(out_path)
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    species = str(monster.get("species", "Monster"))
    pairing = _PAIRING_LABEL.get(str(monster.get("pairing", "")), "?")
    banner, bcol = _outcome(result)
    note = (result or {}).get("note", "") or ""
    sprite = monster_art.sprite_b64(species) or _fallback_b64()
    html = _HTML.format(
        sprite=sprite, pairing=_html.escape(pairing),
        banner=_html.escape(banner), bcol=bcol,
        line=_html.escape(f"{monster.get('name', species)}: {note}"[:54]),
    )
    with open(path, "w") as f:
        f.write(html)
    return path
