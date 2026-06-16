"""Gear-sets: themed collections of equipment that grant escalating PvP bonuses
the more pieces you wear.

An :class:`~flippergotchi.game.equipment.Item` belongs to a set via its ``set``
tag (a key in :data:`SETS`). Wearing 2 / 4 / 5 pieces of one set unlocks the
corresponding tier of that set's bonus. Bonuses are returned as a plain dict so
callers can fold them into a duel fighter's power.

CRITICAL: set bonuses affect **PvP duels ONLY**. They must never be consulted by
the WiFi cracking path (game/battle.py) — cracking is deterministic from the
network, not a stat check. This module is pure data + arithmetic; it imports
nothing from the cracking stack.

No persistence here: an item's set membership lives on the item itself (saved by
equipment.Inventory). This module only describes sets and scores loadouts.
"""
from __future__ import annotations

# Each set maps to a theme blurb and three bonus tiers keyed by the minimum
# number of equipped pieces required. A tier is a dict of PvP modifiers:
#   power -> flat add to duel power (folded into pvp_power)
#   atk / def / luck -> stat nudges duel code may read off the loadout
# Tiers are cumulative-by-selection: the *highest reached* threshold wins (we do
# not stack 2-pc + 4-pc); the 4-pc bonus already includes/at least matches 2-pc.
SETS: dict[str, dict] = {
    "Reef Raider": {
        "theme": "Tide-worn salvage of the drowned coast; rewards relentless offense.",
        "tiers": {
            2: {"power": 6, "atk": 2},
            4: {"power": 16, "atk": 5},
            5: {"power": 26, "atk": 8, "luck": 2},
        },
    },
    "Cyber Samurai": {
        "theme": "Disciplined chrome plating; turtle up and outlast them.",
        "tiers": {
            2: {"power": 5, "def": 3},
            4: {"power": 14, "def": 7},
            5: {"power": 24, "def": 10, "atk": 3},
        },
    },
    "Apex Predator": {
        "theme": "Trophy gear of duel champions; all-round dominance.",
        "tiers": {
            2: {"power": 7, "atk": 2, "def": 2},
            4: {"power": 18, "atk": 5, "def": 5, "luck": 2},
            5: {"power": 30, "atk": 8, "def": 8, "luck": 5},
        },
    },
    "Static Coil": {
        "theme": "Crackling scavenged capacitors; swing for the upset.",
        "tiers": {
            2: {"power": 4, "luck": 4},
            4: {"power": 12, "luck": 9},
            5: {"power": 20, "luck": 14, "atk": 3},
        },
    },
}

_STAT_KEYS = ("power", "atk", "def", "luck")


def set_names() -> list[str]:
    """All defined set names (used by equipment.roll_item to tag drops)."""
    return list(SETS)


def describe_set(name: str) -> str:
    """One-line theme blurb for a set, or '' if unknown."""
    s = SETS.get(name)
    return s["theme"] if s else ""


def count_pieces(equipped_items) -> dict[str, int]:
    """How many equipped pieces belong to each set. Items with no/unknown set
    tag are ignored. `equipped_items` is any iterable of objects with a `.set`
    attribute (or dicts with a 'set' key)."""
    counts: dict[str, int] = {}
    for it in equipped_items or []:
        tag = getattr(it, "set", None)
        if tag is None and isinstance(it, dict):
            tag = it.get("set")
        if tag and tag in SETS:
            counts[tag] = counts.get(tag, 0) + 1
    return counts


def _tier_for(set_name: str, pieces: int) -> dict:
    """The best (highest threshold <= pieces) bonus tier for one set."""
    tiers = SETS.get(set_name, {}).get("tiers", {})
    best: dict = {}
    for need in sorted(tiers):
        if pieces >= need:
            best = tiers[need]
    return best


def set_bonus(equipped_items) -> dict:
    """Aggregate PvP bonus across every set the loadout partially completes.

    Returns {"power": int, "atk": int, "def": int, "luck": int} with zeros
    omitted-as-zero (always present so callers can `.get(...)` freely). If a
    loadout mixes two sets that each hit their 2-pc tier, both contribute.
    PvP ONLY — never feed this into cracking.
    """
    total = {k: 0 for k in _STAT_KEYS}
    for name, pieces in count_pieces(equipped_items).items():
        tier = _tier_for(name, pieces)
        for k in _STAT_KEYS:
            total[k] += int(tier.get(k, 0))
    return total


def describe(equipped_items) -> str:
    """Human-readable summary of active set bonuses for a loadout."""
    counts = count_pieces(equipped_items)
    if not counts:
        return "No set bonus active."
    lines = []
    for name in sorted(counts):
        pieces = counts[name]
        tier = _tier_for(name, pieces)
        if tier:
            parts = ", ".join(f"+{v} {k}" for k, v in tier.items() if v)
            lines.append(f"{name} ({pieces} pc): {parts}")
        else:
            lines.append(f"{name} ({pieces} pc): need 2 for a bonus")
    return " | ".join(lines)
