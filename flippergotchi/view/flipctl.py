from __future__ import annotations

import os

from ..pet import mechanics
from .faces import face

# A 256x144 "screen" mock-up in Flipper orange. On the device this same markup
# is what a FlipCTL view renders to the LCD (FlipCTL uses an HTML/CSS backend),
# and it doubles as the web/TUI frontend during development.
# TODO: register as a real FlipCTL plugin + map D-pad/soft-buttons to actions.
_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>{name}</title><style>
  html,body{{margin:0;background:#222;}}
  .screen{{width:256px;height:144px;background:#FF8200;color:#161616;
    font-family:monospace;padding:6px;box-sizing:border-box;}}
  .hdr{{font-size:11px;font-weight:bold;}}
  .face{{white-space:pre;font-size:9px;line-height:9px;margin:2px 0;}}
  .row{{font-size:9px;margin-top:1px;}}
  .bar{{display:inline-block;background:#161616;height:5px;vertical-align:middle;}}
  .say{{font-size:9px;font-style:italic;margin-top:3px;}}
</style></head><body>
  <div class="screen">
    <div class="hdr">{name} Lv.{level} {stage} - {mood}</div>
    <div class="face">{face}</div>
    <div class="row">food <span class="bar" style="width:{food}px"></span></div>
    <div class="row">enrg <span class="bar" style="width:{energy}px"></span></div>
    <div class="row">{hs} hs - {pm} pmkid - {dist:.0f}m walked</div>
    <div class="say">{name}: {line}</div>
  </div>
</body></html>"""


def render(state, cfg, line: str = "", mood_override: str | None = None) -> str:
    path = os.path.expanduser(cfg.flipctl_html_out)
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    m = mood_override or mechanics.mood(state)
    html = _HTML.format(
        name=state.name, level=state.level, stage=state.stage, mood=m,
        face=face(m),
        food=int(max(0.0, 100 - state.hunger)),
        energy=int(max(0.0, state.energy)),
        hs=state.handshakes, pm=state.pmkids, dist=state.distance_m,
        line=('"' + line.replace('"', "'") + '"') if line else "",
    )
    with open(path, "w") as f:
        f.write(html)
    return path
