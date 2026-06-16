"""Original vector mascot for the LCD — a badass cartoon shark (Street-Sharks
'90s vibe): evolutions, moods, and wearable equipment.

Drawn in a 220x220 SVG space, scaled to the 256x144 screen. It changes shape
across the evolution stages (egg -> hatchling -> fingerling -> juvenile -> adult
-> alpha -> legend) and wears gear on distinct zones (head / brow / neck / chest
/ shoulder) so up to five slots read even when small.

ORIGINAL art — not based on any trademarked logo. See the README trademark note.
"""
from __future__ import annotations

import itertools

_OUT = '#1d2a33'
# unique suffix per render so multiple mascots on one page don't share gradient
# / clip / filter ids (url(#body) is document-global and would otherwise collide)
_uid = itertools.count(1)
_MOUTH = '#3a2230'
_TONGUE = '#d9617a'

# color/pattern variants — original art whose palettes nod to classic '90s
# shark-toon characters (names kept descriptive; those characters are
# third-party trademarks). b=body gradient, f=fin gradient, belly=throat, pat=skin
_PAL = {
    "classic": dict(b=("#86a9bb", "#5f8294", "#4a6b7c"), f=("#6f93a6", "#4a6b7c"),
                    belly=("#eef5f8", "#cfe0e8"), pat=None),
    "blue":    dict(b=("#5b8fc9", "#3f6aa3", "#2f5180"), f=("#4d7cb5", "#2f5180"),
                    belly=("#f0e4c8", "#e6d4ad"), pat=None),       # great-white, beige belly
    "tiger":   dict(b=("#8fc4e8", "#6aa6d6", "#4f86bd"), f=("#79b3df", "#4f86bd"),
                    belly=("#eef5fb", "#d4e6f4"), pat="stripes"),  # light blue + purple stripes
    "gold":    dict(b=("#e8c453", "#c79e2e", "#a8821f"), f=("#d4b23e", "#a8821f"),
                    belly=("#e8ecee", "#cfd6da"), pat=None),       # gold, grey belly
    "reef":    dict(b=("#f3974a", "#e0792a", "#c5631a"), f=("#e8853a", "#c5631a"),
                    belly=("#ffe9d6", "#f4d2b4"), pat="spots"),    # orange + peach spots
}
VARIANTS = list(_PAL)

_HEAD_D = "M110 42 C154 44 182 78 180 112 C178 140 152 160 110 162 C68 160 42 140 40 112 C38 78 66 44 110 42 Z"
_TORSO_D = "M18 212 C22 166 52 148 86 150 L134 150 C168 148 198 166 202 212 Z"


def _defs(variant):
    p = _PAL.get(variant, _PAL["classic"])
    b, f, be = p["b"], p["f"], p["belly"]
    return ('<defs>'
            f'<linearGradient id="body" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{b[0]}"/>'
            f'<stop offset=".55" stop-color="{b[1]}"/><stop offset="1" stop-color="{b[2]}"/></linearGradient>'
            f'<linearGradient id="fin" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{f[0]}"/>'
            f'<stop offset="1" stop-color="{f[1]}"/></linearGradient>'
            f'<radialGradient id="belly" cx=".5" cy=".4" r=".7"><stop offset="0" stop-color="{be[0]}"/>'
            f'<stop offset="1" stop-color="{be[1]}"/></radialGradient>'
            '<filter id="glow" x="-80%" y="-80%" width="260%" height="260%"><feGaussianBlur stdDeviation="4"/></filter>'
            f'<clipPath id="silho"><path d="{_HEAD_D}"/><path d="{_TORSO_D}"/></clipPath>'
            '</defs>')


def _pattern(variant):
    pat = _PAL.get(variant, {}).get("pat")
    if pat == "stripes":
        bars = "".join(f'<path d="M{x} 52 q-9 54 0 110" stroke="#6e46a8" stroke-width="7" fill="none" opacity=".8"/>'
                       for x in (72, 96, 124, 148))
        return f'<g clip-path="url(#silho)">{bars}</g>'
    if pat == "spots":
        pts = [(68, 70), (152, 70), (58, 102), (162, 102), (90, 58), (130, 58),
               (44, 184), (176, 184), (78, 204), (142, 204), (110, 210)]
        dots = "".join(f'<circle cx="{x}" cy="{y}" r="6" fill="#ffe2c2" opacity=".9"/>' for x, y in pts)
        return f'<g clip-path="url(#silho)">{dots}</g>'
    return ""


_TORSO = (
    f'<path d="{_TORSO_D}" fill="url(#body)" stroke="{_OUT}" stroke-width="5" stroke-linejoin="round"/>'
    f'<ellipse cx="48" cy="176" rx="26" ry="22" fill="url(#body)" stroke="{_OUT}" stroke-width="4"/>'
    f'<ellipse cx="172" cy="176" rx="26" ry="22" fill="url(#body)" stroke="{_OUT}" stroke-width="4"/>'
    '<path d="M88 158 Q110 150 132 158 Q134 188 110 196 Q86 188 88 158Z" fill="url(#belly)"/>'
)

_HEAD = (
    f'<path d="{_HEAD_D}" fill="url(#body)" stroke="{_OUT}" stroke-width="5" stroke-linejoin="round"/>'
    '<path d="M80 116 Q110 104 140 116 Q142 146 110 156 Q78 146 80 116Z" fill="url(#belly)"/>'
)

_GILLS = (
    f'<path d="M50 104 q7 10 0 20 M58 102 q7 10 0 20 M66 101 q7 10 0 20" fill="none" stroke="{_OUT}" stroke-width="3" stroke-linecap="round"/>'
    f'<path d="M170 104 q-7 10 0 20 M162 102 q-7 10 0 20 M154 101 q-7 10 0 20" fill="none" stroke="{_OUT}" stroke-width="3" stroke-linecap="round"/>'
)

_HEADFIN_N = f'<path d="M96 50 C98 16 120 0 136 8 C130 28 130 46 136 54 Z" fill="url(#fin)" stroke="{_OUT}" stroke-width="4" stroke-linejoin="round"/>'
_HEADFIN_T = f'<path d="M94 52 C96 8 124 -10 142 0 C134 24 132 46 138 56 Z" fill="url(#fin)" stroke="{_OUT}" stroke-width="4" stroke-linejoin="round"/>'
_HEADFIN_H = f'<path d="M92 54 C94 0 130 -22 152 -10 C142 18 136 46 140 58 Z" fill="url(#fin)" stroke="{_OUT}" stroke-width="4" stroke-linejoin="round"/>'


def _headfin(stage):
    if stage == "adult":
        return _HEADFIN_T
    if stage in ("alpha", "legend"):
        return _HEADFIN_H
    return _HEADFIN_N


_SCALE = {"hatchling": 0.62, "fingerling": 0.82, "juvenile": 1.0,
          "adult": 1.06, "alpha": 1.12, "legend": 1.15}
_ANTENNA_SHIFT = {"adult": (6, 1), "alpha": (10, 2), "legend": (12, 2)}

# --- face pieces -----------------------------------------------------------
_BROW = (f'<path d="M62 84 L104 98" stroke="{_OUT}" stroke-width="8" stroke-linecap="round"/>'
         f'<path d="M158 84 L116 98" stroke="{_OUT}" stroke-width="8" stroke-linecap="round"/>')
_BROW_UP = (f'<path d="M64 90 L104 92" stroke="{_OUT}" stroke-width="8" stroke-linecap="round"/>'
            f'<path d="M156 90 L116 92" stroke="{_OUT}" stroke-width="8" stroke-linecap="round"/>')
_EYES = (f'<path d="M70 100 L98 106 L93 117 L72 112 Z" fill="#fff" stroke="{_OUT}" stroke-width="3" stroke-linejoin="round"/>'
         f'<path d="M150 100 L122 106 L127 117 L148 112 Z" fill="#fff" stroke="{_OUT}" stroke-width="3" stroke-linejoin="round"/>'
         f'<circle cx="86" cy="108" r="4.5" fill="{_OUT}"/><circle cx="134" cy="108" r="4.5" fill="{_OUT}"/>')
_EYES_FLAT = (f'<path d="M72 110 H96" stroke="{_OUT}" stroke-width="4" stroke-linecap="round"/>'
              f'<path d="M148 110 H124" stroke="{_OUT}" stroke-width="4" stroke-linecap="round"/>')
_EYES_CLOSED = (f'<path d="M72 106 Q84 114 96 108" fill="none" stroke="{_OUT}" stroke-width="4" stroke-linecap="round"/>'
                f'<path d="M148 106 Q136 114 124 108" fill="none" stroke="{_OUT}" stroke-width="4" stroke-linecap="round"/>')
_EYES_X = (f'<path d="M74 102 l18 12 M92 102 l-18 12" stroke="{_OUT}" stroke-width="4" stroke-linecap="round"/>'
           f'<path d="M128 102 l18 12 M146 102 l-18 12" stroke="{_OUT}" stroke-width="4" stroke-linecap="round"/>')
_NOSE = f'<path d="M101 116 l-3 5 M119 116 l3 5" stroke="{_OUT}" stroke-width="2.5" stroke-linecap="round"/>'

_UTEETH = f'<path d="M76 127 l8 12 8 -12 8 12 8 -12 8 12 8 -12 8 12 8 -12 L144 127 Z" fill="#fff" stroke="{_OUT}" stroke-width="1.5" stroke-linejoin="round"/>'
_LTEETH = f'<path d="M84 155 l7 -10 7 10 7 -10 7 10 7 -10 7 10 L138 155 Z" fill="#fff" stroke="{_OUT}" stroke-width="1.5" stroke-linejoin="round"/>'
_MOUTH_GRIN = (f'<path d="M72 126 Q110 120 148 126 Q152 146 110 156 Q68 146 72 126 Z" fill="{_MOUTH}"/>'
               f'<ellipse cx="110" cy="150" rx="14" ry="6" fill="{_TONGUE}"/>' + _UTEETH + _LTEETH)
_MOUTH_CHOMP = (f'<path d="M70 122 Q110 113 150 122 Q156 150 110 164 Q64 150 70 122 Z" fill="{_MOUTH}"/>'
                f'<ellipse cx="110" cy="156" rx="15" ry="7" fill="{_TONGUE}"/>'
                f'<path d="M74 123 l9 14 9 -14 9 14 9 -14 9 14 9 -14 9 14 9 -14 L146 123 Z" fill="#fff" stroke="{_OUT}" stroke-width="1.5" stroke-linejoin="round"/>'
                f'<path d="M82 163 l8 -12 8 12 8 -12 8 12 8 -12 8 12 L138 163 Z" fill="#fff" stroke="{_OUT}" stroke-width="1.5" stroke-linejoin="round"/>')
_MOUTH_SMIRK = (f'<path d="M80 134 Q112 146 142 132" fill="none" stroke="{_OUT}" stroke-width="5" stroke-linecap="round"/>'
                f'<path d="M126 138 l3 8 4 -7Z" fill="#fff" stroke="{_OUT}" stroke-width="1.5" stroke-linejoin="round"/>')
_MOUTH_WAVY = f'<path d="M82 138 q9 -8 18 0 q9 8 18 0 q9 -8 18 0" fill="none" stroke="{_OUT}" stroke-width="4" stroke-linecap="round"/>'
_DROOL = f'<path d="M124 154 q3 10 0 15 q-3 -5 0 -15Z" fill="{_TONGUE}"/>'
_SWEAT = '<path d="M156 92 q5 9 0 13 q-5 -4 0 -13Z" fill="#8fd0ff" stroke="#4aa3e0" stroke-width="1.5"/>'
_ZZZ = f'<text x="152" y="74" font-family="monospace" font-size="22" font-weight="700" fill="{_OUT}">z</text>'
_STAR = '<path d="M%d %d l3 7 7 3 -7 3 -3 7 -3-7 -7-3 7-3Z" fill="#fff" stroke="%s" stroke-width="1.5"/>'


def _face(mood):
    if mood == "sleeping":
        return _EYES_CLOSED + _NOSE + _MOUTH_SMIRK + _ZZZ
    if mood == "sick":
        return _EYES_X + _NOSE + _MOUTH_WAVY
    if mood == "tired":
        return _BROW_UP + _EYES_FLAT + _NOSE + _MOUTH_SMIRK
    if mood in ("excited",):
        return (_BROW_UP + _EYES + _NOSE + _MOUTH_CHOMP
                + (_STAR % (40, 76, _OUT)) + (_STAR % (176, 80, _OUT)))
    if mood == "eating":
        return _BROW + _EYES + _NOSE + _MOUTH_CHOMP
    if mood == "hungry":
        return _BROW_UP + _EYES + _NOSE + _MOUTH_GRIN + _DROOL + _SWEAT
    # content / happy / walking / default — confident toothy grin
    return _BROW + _EYES + _NOSE + _MOUTH_GRIN


def _scar(stage):
    if stage in ("alpha", "legend"):
        return f'<path d="M64 78 L92 120" stroke="{_OUT}" stroke-width="2.5" stroke-linecap="round"/><path d="M70 88 l8 -4 M76 100 l8 -4" stroke="{_OUT}" stroke-width="2" stroke-linecap="round"/>'
    return ""


def _aura(stage):
    if stage == "legend":
        return '<ellipse cx="110" cy="120" rx="104" ry="106" fill="#fff0bf" opacity=".4"/>'
    return ""


def _egg():
    # a shark "mermaid's purse" egg case
    return (f'<path d="M78 60 l-14 -16 M142 60 l14 -16 M78 188 l-14 16 M142 188 l14 16" stroke="{_OUT}" stroke-width="3" stroke-linecap="round" fill="none"/>'
            f'<path d="M76 56 Q110 44 144 56 Q160 124 144 192 Q110 204 76 192 Q60 124 76 56 Z" fill="#6f5a3a" stroke="{_OUT}" stroke-width="5" stroke-linejoin="round"/>'
            '<path d="M92 70 Q110 64 128 70 Q138 124 128 178 Q110 184 92 178 Q82 124 92 70Z" fill="#7d6743" opacity=".7"/>'
            f'<path d="M110 70 V178" stroke="{_OUT}" stroke-width="2" opacity=".4"/>')


# --- equipment -------------------------------------------------------------
RARITY_COLOR = {"common": "#b8c2cb", "uncommon": "#7fd1a6", "rare": "#5aa9ff",
                "epic": "#c07bf0", "legendary": "#ffcf4d"}


def _glow(slot, color):
    f = f'fill="{color}" filter="url(#glow)" opacity=".85"'
    return {
        "antenna": f'<circle cx="161" cy="15" r="12" {f}/>',
        "cpu": f'<rect x="80" y="68" width="60" height="14" rx="7" {f}/>',
        "charm": f'<circle cx="110" cy="170" r="12" {f}/>',
        "hull": f'<path d="M74 162 Q110 178 146 162 L142 196 Q110 208 78 196Z" {f}/>',
        "battery": f'<rect x="160" y="166" width="22" height="22" rx="5" {f}/>',
    }.get(slot, "")


def _gear(slot, color, glow=False):
    halo = _glow(slot, color) if glow else ""
    if slot == "antenna":     # antler-like aerial off the top of the head
        return (halo + f'<line x1="148" y1="58" x2="160" y2="16" stroke="{_OUT}" stroke-width="5" stroke-linecap="round"/>'
                f'<circle cx="161" cy="15" r="7" fill="{color}" stroke="{_OUT}" stroke-width="3"/>')
    if slot == "cpu":          # bandana headband across the forehead
        return (halo + f'<path d="M64 78 Q110 66 156 78 L156 70 Q110 58 64 70 Z" fill="#3a4a55" stroke="{_OUT}" stroke-width="3" stroke-linejoin="round"/>'
                f'<circle cx="110" cy="70" r="5" fill="{color}" stroke="{_OUT}" stroke-width="2"/>'
                f'<path d="M64 74 l-12 6 6 8" fill="#3a4a55" stroke="{_OUT}" stroke-width="3" stroke-linejoin="round"/>')
    if slot == "charm":        # chunky chain necklace + pendant
        return (halo + f'<path d="M80 150 Q110 172 140 150" fill="none" stroke="#caa64a" stroke-width="5" stroke-dasharray="2 3" stroke-linecap="round"/>'
                f'<path d="M110 164 l8 10 -8 9 -8 -9Z" fill="{color}" stroke="{_OUT}" stroke-width="2.5" stroke-linejoin="round"/>')
    if slot == "hull":         # chest armor plate
        return (halo + f'<path d="M74 162 Q110 178 146 162 L142 196 Q110 208 78 196Z" fill="{color}" stroke="{_OUT}" stroke-width="3" stroke-linejoin="round"/>'
                f'<line x1="110" y1="172" x2="110" y2="200" stroke="{_OUT}" stroke-width="2.5"/>'
                f'<circle cx="92" cy="180" r="2.5" fill="{_OUT}"/><circle cx="128" cy="180" r="2.5" fill="{_OUT}"/>')
    if slot == "battery":      # gadget on the right shoulder
        return (halo + f'<rect x="160" y="166" width="22" height="24" rx="4" fill="#3a4a55" stroke="{_OUT}" stroke-width="3"/>'
                f'<rect x="167" y="162" width="8" height="5" rx="1.5" fill="{_OUT}"/>'
                f'<rect x="164" y="172" width="14" height="4" rx="2" fill="{color}"/>'
                f'<rect x="164" y="179" width="14" height="4" rx="2" fill="{color}"/>')
    return ""


def mascot_svg(mood: str = "content", equipped: dict | None = None,
               stage: str = "juvenile", variant: str = "classic") -> str:
    """Inner SVG (for viewBox='0 0 220 220') of the shark at this evolution
    stage, in this mood, wearing `equipped` (slot -> rarity), in colour `variant`
    (one of VARIANTS)."""
    defs = _defs(variant)
    if stage == "egg":
        return _uniq(defs + _egg())
    equipped = equipped or {}
    parts = [_aura(stage)]
    if "antenna" in equipped:
        rarity = equipped["antenna"]
        ant = _gear("antenna", RARITY_COLOR.get(rarity, "#b8c2cb"), rarity == "legendary")
        dx, dy = _ANTENNA_SHIFT.get(stage, (0, 0))
        if dx or dy:
            ant = f'<g transform="translate({dx} {dy})">{ant}</g>'
        parts.append(ant)
    parts += [_headfin(stage), _TORSO, _HEAD, _pattern(variant), _GILLS,
              _face(mood), _scar(stage)]
    for slot in ("cpu", "charm", "hull", "battery"):
        if slot in equipped:
            rarity = equipped[slot]
            parts.append(_gear(slot, RARITY_COLOR.get(rarity, "#b8c2cb"),
                               rarity == "legendary"))
    s = _SCALE.get(stage, 1.0)
    inner = "".join(parts)
    g = f'<g transform="translate(110 120) scale({s}) translate(-110 -120)">{inner}</g>'
    return _uniq(defs + g)


def _uniq(svg: str) -> str:
    """Suffix the shared ids so several mascots can share one HTML document."""
    u = f"_{next(_uid)}"
    for name in ("body", "fin", "belly", "glow", "silho"):
        svg = svg.replace(f'id="{name}"', f'id="{name}{u}"')
        svg = svg.replace(f'url(#{name})', f'url(#{name}{u})')
    return svg
