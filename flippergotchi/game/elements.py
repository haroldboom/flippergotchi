"""Elemental type-advantage chart for Flippergotchi duels.

Each Flippergotchi (and the monsters it collects) carries an ``element`` drawn
from the radio band it was born on:

    2.4GHz -> "Spark"   (long range, noisy, aggressive)
    5GHz   -> "Tide"    (fast, dense, flowing)
    6GHz   -> "Gale"    (modern, sharp, high-frequency)
    BLE    -> "Aether"  (the quirky low-energy wildcard)

The three "band" elements form a rock-paper-scissors cycle; Aether sits
outside it as a neutral-but-quirky element.

The cycle (attacker BEATS defender):

    Spark > Gale > Tide > Spark

Read it as: Spark's wide reach overpowers Gale's narrow band; Gale's high
frequency cuts through Tide's density; Tide's flow drowns out Spark's noise.

Aether is deliberately *quirky* rather than purely neutral:
  * Aether is **strong** against Spark (the low-energy ghost slips past the
    loud, brute-force element), and
  * Aether is **weak** against Gale (sharp high-frequency winds scatter it).
  * Against Tide, and against itself, Aether is neutral.

All of this is expressed as data in ``_BEATS`` (the set of ordered
``(attacker, defender)`` pairs where the attacker has the advantage). The
reverse of every such pair is automatically the disadvantaged matchup, so the
chart is anti-symmetric by construction.
"""
from __future__ import annotations

ELEMENTS = ["Spark", "Tide", "Gale", "Aether"]

# Tunable multipliers.
STRONG = 1.25   # attacker has the type advantage
WEAK = 0.8      # attacker is at the type disadvantage
NEUTRAL = 1.0   # no advantage either way (or an unknown/None element)

# Ordered (attacker, defender) pairs where the ATTACKER is strong.
# The reverse of each pair is therefore the WEAK matchup.
_BEATS = {
    ("Spark", "Gale"),    # band cycle: Spark > Gale
    ("Gale", "Tide"),     # band cycle: Gale  > Tide
    ("Tide", "Spark"),    # band cycle: Tide  > Spark
    ("Aether", "Spark"),  # quirk: Aether slips past Spark
    ("Gale", "Aether"),   # quirk: Gale scatters Aether
}


def advantage_multiplier(attacker: str, defender: str) -> float:
    """Damage/odds multiplier for ``attacker`` hitting ``defender``.

    Returns ``STRONG`` (~1.25) when the attacker has the type advantage,
    ``WEAK`` (~0.8) when at a disadvantage, and ``NEUTRAL`` (1.0) when the
    matchup is neutral or either element is unknown/``None``.
    """
    if not attacker or not defender:
        return NEUTRAL
    if attacker not in ELEMENTS or defender not in ELEMENTS:
        return NEUTRAL
    if (attacker, defender) in _BEATS:
        return STRONG
    if (defender, attacker) in _BEATS:
        return WEAK
    return NEUTRAL


def matchup_note(attacker: str, defender: str) -> str:
    """Short human label for the matchup: "strong" / "weak" / "neutral"."""
    m = advantage_multiplier(attacker, defender)
    if m > NEUTRAL:
        return "strong"
    if m < NEUTRAL:
        return "weak"
    return "neutral"
