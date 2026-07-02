"""Visual achievement badge-wall, authored at the Flipper One's native 256x144.

The whole catalogue laid out as a wall, grouped by category. Each badge shows a
tier mark (B/S/G), a star when unlocked, and -- for locked badges -- a small
progress hint (current/threshold from achievements.progress). Hidden badges stay
masked behind achievements.display_name until earned. This is a READ-ONLY render:
it reflects the book's state and the caller-supplied stats snapshot, never
unlocking or paying anything.

Mirrors view/feed_screen.py for structure/CSS (a .screen div, filter:grayscale(1),
DejaVu Sans Mono). Scaled up nearest-neighbour by the caller, same pipeline as the
other screens.
"""
from __future__ import annotations

import html as _html

from ..game import achievements as ach_mod
from . import sink

_TIER = {"bronze": "B", "silver": "S", "gold": "G", "": "-"}


_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><style>
  html,body{{margin:0;background:#000;}}
  *{{box-sizing:border-box;image-rendering:pixelated;}}
  .screen{{filter:grayscale(1);image-rendering:pixelated;width:256px;height:144px;position:relative;
    overflow:hidden;font-family:'DejaVu Sans Mono',monospace;color:#eaf2ff;
    background:linear-gradient(#13213e 0%,#0d1730 55%,#0a1226 100%);}}
  .title{{position:absolute;top:4px;left:6px;font-size:9px;font-weight:800;
    letter-spacing:1px;color:#aee3ff;z-index:3;}}
  .count{{position:absolute;top:5px;right:6px;font-size:8px;font-weight:800;
    color:#9fb6d6;z-index:3;}}
  .wall{{position:absolute;top:16px;left:4px;right:4px;bottom:4px;overflow:hidden;
    columns:2;column-gap:6px;}}
  .cat{{font-size:7px;font-weight:800;color:#7ddfff;letter-spacing:.5px;
    margin:1px 0;break-inside:avoid;}}
  .badge{{display:flex;align-items:baseline;gap:2px;break-inside:avoid;
    font-size:7px;font-weight:700;line-height:1.25;}}
  .badge.locked{{color:#6b7790;}}
  .star{{color:#ffd24a;font-weight:800;width:7px;}}
  .lock{{color:#46506a;width:7px;}}
  .tier{{color:#9fb6d6;font-weight:800;}}
  .nm{{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}}
  .prog{{color:#5f86b8;font-weight:800;}}
</style></head><body>
  <div class="screen">
    <div class="title">&#127942; BADGES</div>
    <div class="count">{got}/{total}</div>
    <div class="wall">{rows}</div>
  </div>
</body></html>"""


def render_html(book, stats, state) -> str:
    """Build the 256x144 badge wall document as a string (pure; no I/O).

    ``book`` is a game.achievements.AchievementBook; ``stats`` the read-only
    progress snapshot (achievements.build_stats); ``state`` the PetState (used
    only for the active title line). Pure render -- no unlock, no grant."""
    rows = ""
    last_cat = None
    for b in book.all():
        got = book.is_unlocked(b.id)
        if b.category != last_cat:
            rows += f"<div class='cat'>-- {_html.escape(b.category)} --</div>"
            last_cat = b.category
        name = ach_mod.display_name(b, got)
        cls = "badge" if got else "badge locked"
        mark = "<span class='star'>&#9733;</span>" if got \
            else "<span class='lock'>&middot;</span>"
        tier = _TIER.get(b.tier, "-")
        hint = ""
        if not got and not b.hidden:
            cur, thr = ach_mod.progress(b, stats)
            hint = f"<span class='prog'>{int(cur)}/{int(thr)}</span>"
        rows += (f"<div class='{cls}'>{mark}"
                 f"<span class='tier'>{tier}</span>"
                 f"<span class='nm'>{_html.escape(name)}</span>{hint}</div>")

    got, total = book.progress()
    return _HTML.format(rows=rows, got=got, total=total)


def render(out_path: str, book, stats, state) -> str:
    """Write the 256x144 badge wall to ``out_path``. Returns out_path."""
    return sink.write(out_path, render_html(book, stats, state))
