"""Move set for Digimon-style Flippergotchi duels.

The duel engine (``game/duel.py``) drives a short turn-based fight where each
fighter repeatedly *picks a move* and *applies it* against the opponent. This
module holds that move data plus the pure helpers the engine calls:

    moves_for(element)                  -> list[Move]   (element kit + universals)
    pick_move(fighter, rng)             -> Move         (simple policy)
    apply_move(attacker, defender, move, rng, advantage) -> dict

Everything is deterministic under an injected ``rng`` (anything with
``random()`` / ``randint()`` -- the stdlib ``random`` module, or a seeded
``random.Random``). Nothing here mutates the fighters; the engine owns HP and
status bookkeeping. ``apply_move`` just reports what *would* happen as a dict
of {damage, effects_applied, log_line, hit}.

Move shape (a frozen dataclass):

    id        short stable identifier ("spark_bolt")
    name      display name ("Static Bolt")
    element   one of elements.ELEMENTS, or "" for a universal move
    power     base damage before type-advantage / variance (0 for pure status)
    accuracy  hit probability in 0..1
    effect    optional status keyword (see EFFECTS), or "" for none
    chance    probability the effect procs on a hit (0..1)

Status effect keywords (interpreted by the duel engine):

    stun     defender skips their next turn
    bleed    damage-over-time on the defender for a few turns
    corrupt  damage-over-time on the defender for a few turns (heavier, shorter)
    shield   raise the *attacker's* defence for a few turns (incoming dmg down)
    buff     raise the *attacker's* attack for a few turns (outgoing dmg up)
    drain    attacker heals a fraction of the damage dealt
"""
from __future__ import annotations

from dataclasses import dataclass

from .elements import ELEMENTS

# Recognised status keywords (the engine knows how to resolve each).
EFFECTS = ("stun", "bleed", "corrupt", "shield", "buff", "drain")

# Critical hits: if the attacker exposes a positive ``crit_chance`` (the duel
# engine derives it from equipped LUCK), damaging hits may crit for extra
# damage. Attackers without the attribute never roll, so seeded sequences for
# stat-less fighters are unchanged. R2/R3 rebalance: 1.5 -> 1.8 so a
# capped-crit LUCK build's expected damage rivals an equal-budget ATK build
# (LUCK was a trap stat -- see docs/playtest-notes.md).
CRIT_MULT = 1.8


@dataclass(frozen=True)
class Move:
    """A single attack/utility option in a duel."""
    id: str
    name: str
    element: str          # "" == universal (no STAB / type multiplier)
    power: float
    accuracy: float
    effect: str = ""      # one of EFFECTS, or "" for none
    chance: float = 0.0   # probability the effect procs on a successful hit


# ---------------------------------------------------------------------------
# Move tables: 3-4 per element + a couple of universals everyone can use.
# Kept compact and roughly balanced (power ~ inverse of accuracy/utility).
# ---------------------------------------------------------------------------
_ELEMENT_MOVES: dict[str, list[Move]] = {
    "Spark": [
        Move("spark_bolt", "Static Bolt", "Spark", 14, 0.95),
        Move("spark_overload", "Overload", "Spark", 22, 0.75, "stun", 0.30),
        Move("spark_arc", "Arc Surge", "Spark", 18, 0.85, "bleed", 0.35),
        Move("spark_charge", "Capacitor Charge", "Spark", 8, 1.0, "buff", 0.80),
    ],
    "Tide": [
        Move("tide_splash", "Packet Splash", "Tide", 13, 0.95),
        Move("tide_riptide", "Riptide", "Tide", 20, 0.80, "drain", 0.50),
        Move("tide_undertow", "Undertow", "Tide", 17, 0.85, "bleed", 0.30),
        Move("tide_wall", "Tide Wall", "Tide", 6, 1.0, "shield", 0.80),
    ],
    "Gale": [
        Move("gale_gust", "Carrier Gust", "Gale", 14, 0.95),
        Move("gale_shear", "Frequency Shear", "Gale", 21, 0.78, "bleed", 0.40),
        Move("gale_cyclone", "Cyclone", "Gale", 19, 0.82, "stun", 0.25),
        Move("gale_tailwind", "Tailwind", "Gale", 9, 1.0, "buff", 0.75),
    ],
    "Aether": [
        Move("aether_whisper", "Null Whisper", "Aether", 13, 0.95),
        Move("aether_corrupt", "Corrupt", "Aether", 16, 0.85, "corrupt", 0.45),
        Move("aether_phase", "Phase Drain", "Aether", 18, 0.82, "drain", 0.45),
        Move("aether_ward", "Spectral Ward", "Aether", 6, 1.0, "shield", 0.75),
    ],
}

# Universal moves -- no element, so no STAB or type multiplier ever applies.
_UNIVERSAL_MOVES: list[Move] = [
    Move("strike", "Antenna Strike", "", 12, 0.90),
    Move("focus", "Focus", "", 0, 1.0, "buff", 1.0),
]


def moves_for(element: str | None) -> list[Move]:
    """Return the move kit for ``element`` plus the universal moves.

    Unknown / ``None`` elements get just the universal kit (always non-empty),
    so callers never have to special-case it.
    """
    kit = list(_ELEMENT_MOVES.get(element or "", []))
    kit.extend(_UNIVERSAL_MOVES)
    return kit


def pick_move(fighter, rng) -> Move:
    """Choose a move for ``fighter`` with a simple, deterministic policy.

    Policy: weight each move by ``power + 6`` so heavy hitters and utility
    moves both get picked, then roll once against the injected ``rng``. Reads
    the fighter's element via ``getattr`` so it works on the duel ``Fighter``
    or any object that exposes ``.element``.
    """
    kit = moves_for(getattr(fighter, "element", ""))
    weights = [m.power + 6.0 for m in kit]
    total = sum(weights)
    if total <= 0:
        return kit[0]
    roll = rng.random() * total
    upto = 0.0
    for move, w in zip(kit, weights):
        upto += w
        if roll < upto:
            return move
    return kit[-1]


def apply_move(attacker, defender, move: Move, rng, advantage: float = 1.0) -> dict:
    """Resolve ``move`` from ``attacker`` against ``defender``.

    ``advantage`` is the elemental multiplier (from ``elements.advantage`` /
    ``advantage_multiplier``) applied to elemental damage. STAB -- a same-type
    bonus when the move's element matches the attacker's -- is folded in too.

    Returns a dict the duel engine consumes:
        {"hit": bool, "damage": float, "effects_applied": list[str],
         "log_line": str}

    Pure: reads attacker/defender stats via ``getattr`` but mutates nothing.
    """
    a_name = getattr(attacker, "name", "?")
    d_name = getattr(defender, "name", "?")

    # Accuracy roll (deterministic under rng).
    if rng.random() > move.accuracy:
        return {
            "hit": False,
            "damage": 0.0,
            "effects_applied": [],
            "log_line": f"{a_name}'s {move.name} missed!",
        }

    mult = 1.0
    note = ""
    if move.element:
        mult *= advantage
        if move.element == getattr(attacker, "element", None):
            mult *= 1.2  # STAB: same-type attack bonus
        if advantage > 1.0:
            note = " (super effective!)"
        elif advantage < 1.0:
            note = " (not very effective)"

    # Attack/defence buffs maintained by the engine on the fighter objects.
    atk_buff = getattr(attacker, "atk_mult", 1.0)
    def_buff = getattr(defender, "def_mult", 1.0)

    base = move.power * mult * atk_buff / max(def_buff, 0.01)
    # Small deterministic variance (85%..100%) so equal fights still vary.
    variance = 0.85 + 0.15 * rng.random()
    damage = round(base * variance, 1) if move.power > 0 else 0.0

    # LUCK-fed critical hit (only rolled when the attacker actually has crit,
    # so legacy fighters consume the exact same rng sequence as before).
    crit_chance = getattr(attacker, "crit_chance", 0.0)
    if damage > 0 and crit_chance > 0 and rng.random() < crit_chance:
        damage = round(damage * CRIT_MULT, 1)
        note += " CRIT!"

    effects: list[str] = []
    if move.effect and rng.random() < move.chance:
        effects.append(move.effect)

    # Compose the blow-by-blow line.
    if move.power > 0:
        line = f"{a_name} uses {move.name}{note} -- {damage:.0f} dmg to {d_name}."
    else:
        line = f"{a_name} uses {move.name}."
    if effects:
        line += " " + _effect_flavour(effects[0], a_name, d_name)

    return {
        "hit": True,
        "damage": float(damage),
        "effects_applied": effects,
        "log_line": line,
    }


def _effect_flavour(effect: str, attacker: str, defender: str) -> str:
    """Short call-out describing a status proc, for the duel log."""
    return {
        "stun": f"{defender} is stunned!",
        "bleed": f"{defender} is bleeding!",
        "corrupt": f"{defender}'s data is corrupted!",
        "shield": f"{attacker} raises a shield!",
        "buff": f"{attacker} powers up!",
        "drain": f"{attacker} drains energy!",
    }.get(effect, "")


__all__ = ["Move", "EFFECTS", "ELEMENTS", "moves_for", "pick_move", "apply_move"]
