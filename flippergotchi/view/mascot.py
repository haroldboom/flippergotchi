"""Original vector mascot for the LCD — evolutions, moods, and wearable gear.

The mascot is drawn in a 220x220 SVG space and scaled to the 256x144 screen.
It changes shape across the evolution stages (egg -> hatchling -> fingerling ->
juvenile -> adult -> alpha -> legend) and wears gear on distinct zones (head /
forehead / neck / belly / side) so up to five slots read even when small.

This is ORIGINAL art (a chunky cartoon cetacean) — deliberately unlike the
trademarked Flipper Devices dolphin logo. See the README trademark note.
"""
from __future__ import annotations

_OUT = '#27343d'

_DEFS = (
    '<defs>'
    '<linearGradient id="body" x1="0" y1="0" x2="0" y2="1">'
    '<stop offset="0" stop-color="#f4f8fb"/><stop offset=".55" stop-color="#cfe0ea"/>'
    '<stop offset="1" stop-color="#a9c6d6"/></linearGradient>'
    '<linearGradient id="fin" x1="0" y1="0" x2="0" y2="1">'
    '<stop offset="0" stop-color="#9db9c8"/><stop offset="1" stop-color="#7ba0b3"/></linearGradient>'
    '<radialGradient id="belly" cx=".5" cy=".35" r=".7">'
    '<stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#eaf3f8"/></radialGradient>'
    '</defs>'
)

# pectoral fins + tail flukes (behind body)
_FINS = (
    f'<path d="M110 150 C150 150 178 170 196 196 C170 188 150 188 132 196 C124 178 116 164 110 150Z" fill="url(#fin)" stroke="{_OUT}" stroke-width="4" stroke-linejoin="round"/>'
    f'<path d="M110 150 C70 150 42 170 24 196 C50 188 70 188 88 196 C96 178 104 164 110 150Z" fill="url(#fin)" stroke="{_OUT}" stroke-width="4" stroke-linejoin="round"/>'
    f'<path d="M60 150 C40 150 26 168 22 186 C44 178 58 168 70 152Z" fill="url(#fin)" stroke="{_OUT}" stroke-width="4" stroke-linejoin="round"/>'
    f'<path d="M160 150 C180 150 194 168 198 186 C176 178 162 168 150 152Z" fill="url(#fin)" stroke="{_OUT}" stroke-width="4" stroke-linejoin="round"/>'
)

# body core (ellipse + belly + blowhole + cheeks) — no fins, no dorsal, no face
_CORE = (
    f'<ellipse cx="110" cy="120" rx="72" ry="76" fill="url(#body)" stroke="{_OUT}" stroke-width="5"/>'
    '<ellipse cx="110" cy="138" rx="48" ry="50" fill="url(#belly)"/>'
    f'<ellipse cx="110" cy="64" rx="5" ry="3" fill="{_OUT}"/>'
    '<circle cx="74" cy="126" r="11" fill="#ff8aa0" opacity=".45"/>'
    '<circle cx="146" cy="126" r="11" fill="#ff8aa0" opacity=".45"/>'
)

# ----- evolution: scale + dorsal fin + crest + markings + aura per stage -----
_SCALE = {"hatchling": 0.64, "fingerling": 0.82, "juvenile": 1.0,
          "adult": 1.06, "alpha": 1.12, "legend": 1.15}

_DORSAL_NORMAL = f'<path d="M96 56 C100 26 112 12 122 14 C128 30 126 46 128 58Z" fill="url(#fin)" stroke="{_OUT}" stroke-width="4" stroke-linejoin="round"/>'
_DORSAL_TALL = f'<path d="M94 58 C98 18 112 0 124 4 C130 26 128 46 130 60Z" fill="url(#fin)" stroke="{_OUT}" stroke-width="4" stroke-linejoin="round"/>'
_DORSAL_HUGE = f'<path d="M92 60 C96 8 114 -12 132 -4 C136 22 132 46 134 62Z" fill="url(#fin)" stroke="{_OUT}" stroke-width="4" stroke-linejoin="round"/>'


def _dorsal(stage):
    if stage == "adult":
        return _DORSAL_TALL
    if stage in ("alpha", "legend"):
        return _DORSAL_HUGE
    return _DORSAL_NORMAL


def _crest(stage):
    if stage == "hatchling":   # bit of eggshell still on the head
        return ('<path d="M82 50 l9 -12 9 12 9 -13 9 13 9 -11 5 8 '
                f'q-30 8 -59 0Z" fill="#fdf4dd" stroke="{_OUT}" stroke-width="3" stroke-linejoin="round"/>')
    return ""


def _markings(stage):
    if stage == "alpha":       # fierce brows + a battle scar
        return (f'<path d="M72 84 L98 92" stroke="{_OUT}" stroke-width="5" stroke-linecap="round"/>'
                f'<path d="M148 84 L122 92" stroke="{_OUT}" stroke-width="5" stroke-linecap="round"/>'
                f'<path d="M150 96 l-7 18" stroke="{_OUT}" stroke-width="2.5" stroke-linecap="round"/>')
    if stage == "legend":      # forehead gem + sparkles
        star = '<path d="M%d %d l3 7 7 3 -7 3 -3 7 -3-7 -7-3 7-3Z" fill="#ffe7a0" stroke="%s" stroke-width="1.5"/>'
        return (f'<path d="M110 54 l7 9 -7 9 -7 -9Z" fill="#ffcf4d" stroke="{_OUT}" stroke-width="2"/>'
                + (star % (40, 78, _OUT)) + (star % (178, 84, _OUT)) + (star % (150, 40, _OUT)))
    return ""


def _aura(stage):
    if stage == "legend":
        return '<ellipse cx="110" cy="118" rx="98" ry="102" fill="#fff0bf" opacity=".4"/>'
    return ""


def _egg():
    return (f'<ellipse cx="110" cy="126" rx="56" ry="70" fill="#fdf2da" stroke="{_OUT}" stroke-width="5"/>'
            '<ellipse cx="92" cy="112" rx="11" ry="8" fill="#e7c79a"/>'
            '<ellipse cx="132" cy="140" rx="13" ry="9" fill="#e7c79a"/>'
            '<ellipse cx="116" cy="170" rx="8" ry="6" fill="#e7c79a"/>'
            f'<path d="M86 96 l10 9 -8 9 12 9" fill="none" stroke="{_OUT}" stroke-width="3" stroke-linecap="round"/>'
            '<circle cx="98" cy="120" r="3" fill="%s"/><circle cx="122" cy="120" r="3" fill="%s"/>' % (_OUT, _OUT))


def _eye_open(cx):
    return (f'<ellipse cx="{cx}" cy="106" rx="13" ry="15" fill="#fff" stroke="{_OUT}" stroke-width="3"/>'
            f'<circle cx="{cx-1}" cy="109" r="6.5" fill="{_OUT}"/>'
            f'<circle cx="{cx+2}" cy="106.5" r="2.2" fill="#fff"/>')


def _face(mood):
    happy = (f'<path d="M76 109 Q88 95 100 109" fill="none" stroke="{_OUT}" stroke-width="5" stroke-linecap="round"/>'
             f'<path d="M120 109 Q132 95 144 109" fill="none" stroke="{_OUT}" stroke-width="5" stroke-linecap="round"/>')
    closed = (f'<path d="M78 106 Q88 114 98 106" fill="none" stroke="{_OUT}" stroke-width="4" stroke-linecap="round"/>'
              f'<path d="M122 106 Q132 114 142 106" fill="none" stroke="{_OUT}" stroke-width="4" stroke-linecap="round"/>')
    flat = (f'<path d="M78 107 H98" stroke="{_OUT}" stroke-width="4" stroke-linecap="round"/>'
            f'<path d="M122 107 H142" stroke="{_OUT}" stroke-width="4" stroke-linecap="round"/>')
    xeye = (f'<path d="M80 100 l16 14 M96 100 l-16 14" stroke="{_OUT}" stroke-width="4" stroke-linecap="round"/>'
            f'<path d="M124 100 l16 14 M140 100 l-16 14" stroke="{_OUT}" stroke-width="4" stroke-linecap="round"/>')
    both = _eye_open(88) + _eye_open(132)
    smile = f'<path d="M92 134 Q110 150 128 134" fill="none" stroke="{_OUT}" stroke-width="4.5" stroke-linecap="round"/>'
    big = f'<path d="M86 132 Q110 162 134 132 Q110 150 86 132Z" fill="{_OUT}"/><path d="M104 150 Q110 156 116 150Z" fill="#ff8aa0"/>'
    openm = f'<ellipse cx="110" cy="140" rx="11" ry="9" fill="{_OUT}"/><ellipse cx="110" cy="144" rx="6" ry="3.5" fill="#ff8aa0"/>'
    frown = f'<path d="M92 147 Q110 133 128 147" fill="none" stroke="{_OUT}" stroke-width="4.5" stroke-linecap="round"/>'
    flatm = f'<path d="M97 140 H123" stroke="{_OUT}" stroke-width="4" stroke-linecap="round"/>'
    sweat = '<path d="M150 96 q5 9 0 13 q-5 -4 0 -13Z" fill="#8fd0ff" stroke="#4aa3e0" stroke-width="1.5"/>'
    zzz = f'<text x="150" y="70" font-family="monospace" font-size="22" font-weight="700" fill="{_OUT}">z</text>'
    return {
        "happy": happy + smile,
        "content": both + smile,
        "excited": happy + big,
        "eating": happy + openm,
        "hungry": both + frown + sweat,
        "tired": flat + flatm,
        "sick": xeye + frown,
        "sleeping": closed + flatm + zzz,
        "walking": both + smile,
    }.get(mood, both + smile)


RARITY_COLOR = {"common": "#b8c2cb", "uncommon": "#7fd1a6", "rare": "#5aa9ff",
                "epic": "#c07bf0", "legendary": "#ffcf4d"}


def _gear(slot, color):
    if slot == "antenna":
        return (f'<line x1="138" y1="58" x2="152" y2="12" stroke="{_OUT}" stroke-width="5" stroke-linecap="round"/>'
                f'<circle cx="153" cy="11" r="7" fill="{color}" stroke="{_OUT}" stroke-width="3"/>')
    if slot == "cpu":
        return (f'<rect x="66" y="76" width="88" height="15" rx="7.5" fill="#3a4a55" stroke="{_OUT}" stroke-width="3"/>'
                f'<circle cx="110" cy="83.5" r="5" fill="{color}" stroke="{_OUT}" stroke-width="2"/>')
    if slot == "charm":
        return ('<path d="M82 152 Q110 168 138 152" fill="none" stroke="#caa64a" stroke-width="3"/>'
                f'<path d="M110 160 l7 9 -7 8 -7 -8Z" fill="{color}" stroke="{_OUT}" stroke-width="2.5" stroke-linejoin="round"/>')
    if slot == "hull":
        return (f'<path d="M66 158 Q110 178 154 158 L150 176 Q110 196 70 176Z" fill="{color}" stroke="{_OUT}" stroke-width="3" stroke-linejoin="round"/>'
                f'<line x1="110" y1="168" x2="110" y2="188" stroke="{_OUT}" stroke-width="2.5"/>')
    if slot == "battery":
        return (f'<rect x="24" y="150" width="22" height="30" rx="4" fill="#3a4a55" stroke="{_OUT}" stroke-width="3"/>'
                f'<rect x="31" y="146" width="8" height="5" rx="1.5" fill="{_OUT}"/>'
                f'<rect x="28" y="156" width="14" height="4" rx="2" fill="{color}"/>'
                f'<rect x="28" y="163" width="14" height="4" rx="2" fill="{color}"/>')
    return ""


def mascot_svg(mood: str = "content", equipped: dict | None = None,
               stage: str = "juvenile") -> str:
    """Inner SVG (for viewBox='0 0 220 220') of the mascot at this evolution
    stage, in this mood, wearing `equipped` (slot -> rarity name)."""
    if stage == "egg":
        return _DEFS + _egg()
    equipped = equipped or {}
    parts = [_aura(stage)]
    if "antenna" in equipped:
        parts.append(_gear("antenna", RARITY_COLOR.get(equipped["antenna"], "#b8c2cb")))
    parts += [_dorsal(stage), _FINS, _CORE, _face(mood), _crest(stage), _markings(stage)]
    for slot in ("cpu", "charm", "hull", "battery"):
        if slot in equipped:
            parts.append(_gear(slot, RARITY_COLOR.get(equipped[slot], "#b8c2cb")))
    s = _SCALE.get(stage, 1.0)
    inner = "".join(parts)
    g = f'<g transform="translate(110 120) scale({s}) translate(-110 -120)">{inner}</g>'
    return _DEFS + g
