from __future__ import annotations

import html as _html
import os

from ..pet import mechanics
from .mascot import mascot_svg

# Polished 256x144 LCD screen, rendered as HTML/CSS + an inline SVG mascot.
# On the device this is what the FlipCTL view draws to the LCD; it also doubles
# as the web/dev frontend and is what the README renders are screenshotted from.
# Rendered here at 2x (512x288) for crispness; the layout is the 256x144 design.
# TODO: register as a real FlipCTL plugin + map D-pad/soft-buttons to actions.
_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>{name}</title><style>
  html,body{{margin:0;background:#222;}}
  .screen{{width:512px;height:288px;border-radius:16px;position:relative;
    overflow:hidden;box-sizing:border-box;color:#1f2d36;
    font-family:'DejaVu Sans','Helvetica Neue',sans-serif;
    background:radial-gradient(120% 120% at 50% 0%,#ffa436 0%,#ff8c12 55%,#f07e08 100%);}}
  .top{{position:absolute;top:14px;left:18px;right:18px;display:flex;
    justify-content:space-between;align-items:flex-start;}}
  .name{{font-weight:800;font-size:21px;line-height:1;}}
  .stage{{margin-top:5px;font-size:11px;font-weight:700;opacity:.6;
    text-transform:uppercase;letter-spacing:1px;}}
  .badges{{display:flex;gap:7px;}}
  .chip{{display:flex;align-items:center;gap:4px;background:rgba(31,45,54,.14);
    border-radius:999px;padding:4px 9px;font-size:12px;font-weight:800;}}
  .mascot{{position:absolute;top:28px;left:50%;transform:translateX(-50%);}}
  .stats{{position:absolute;left:18px;right:18px;bottom:52px;display:flex;
    flex-direction:column;gap:7px;}}
  .stat{{display:flex;align-items:center;gap:9px;}}
  .stat .lbl{{width:34px;font-size:11px;font-weight:800;opacity:.7;}}
  .track{{flex:1;height:11px;border-radius:999px;background:rgba(31,45,54,.16);overflow:hidden;}}
  .fill{{height:100%;border-radius:999px;background:linear-gradient(90deg,#2c4350,#1f2d36);}}
  .say{{position:absolute;left:18px;right:18px;bottom:14px;
    background:rgba(255,255,255,.55);border-radius:12px;padding:7px 12px;
    font-size:13px;font-style:italic;font-weight:600;}}
</style></head><body>
  <div class="screen">
    <div class="top">
      <div><div class="name">{name}</div><div class="stage">Lv.{level} · {stage}</div></div>
      <div class="badges">
        <div class="chip"><svg width="13" height="13" viewBox="0 0 24 24"><path fill="#e8556e" d="M12 21s-7-4.6-9.3-9.1C1.1 8.6 2.6 5 6 5c2 0 3.2 1.2 4 2.3C10.8 6.2 12 5 14 5c3.4 0 4.9 3.6 3.3 6.9C19 16.4 12 21 12 21z"/></svg>{health}</div>
        <div class="chip"><svg width="13" height="13" viewBox="0 0 24 24"><path fill="#f3b21b" d="M13 2 4 14h6l-1 8 9-12h-6z"/></svg>{energy}</div>
      </div>
    </div>
    <svg class="mascot" width="150" height="150" viewBox="0 0 220 220">{mascot}</svg>
    <div class="stats">
      <div class="stat"><div class="lbl">FOOD</div><div class="track"><div class="fill" style="width:{food}%"></div></div></div>
      <div class="stat"><div class="lbl">ENRG</div><div class="track"><div class="fill" style="width:{energy}%"></div></div></div>
      <div class="stat"><div class="lbl">XP</div><div class="track"><div class="fill" style="width:{xp}%"></div></div></div>
    </div>
    <div class="say">{name}: {line}</div>
  </div>
</body></html>"""


def render(state, cfg, line: str = "", mood_override: str | None = None,
           equipped: dict | None = None) -> str:
    path = os.path.expanduser(cfg.flipctl_html_out)
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    m = mood_override or mechanics.mood(state)
    nxt = mechanics.xp_to_next(state.level, cfg)
    say = _html.escape(f'"{line}"') if line else ""
    html = _HTML.format(
        name=_html.escape(state.name), level=state.level,
        stage=_html.escape(state.stage.capitalize()),
        mascot=mascot_svg(m, equipped, state.stage,
                          getattr(cfg, "mascot_variant", "classic")),
        health=int(max(0, state.health)), energy=int(max(0, state.energy)),
        food=int(max(0, min(100, 100 - state.hunger))),
        xp=int(max(0, min(100, state.xp / nxt * 100))) if nxt else 0,
        line=say,
    )
    with open(path, "w") as f:
        f.write(html)
    return path
