"""Food kinds the pet forages and eats.

A small catalogue of typed foods. Each kind restores a different amount of
hunger; rarer kinds restore more. ``mechanics.snack`` takes an optional
``kind`` -- with none it falls back
to the flat ``cfg.forage_food`` so every existing caller is byte-identical.

Pure data + helpers, no I/O, no clock reads. Foraging rolls a kind from a
weighted table via a caller-supplied ``rng`` so it stays deterministic/testable.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FoodKind:
    id: str
    name: str
    restore: float        # hunger points removed when eaten
    tier: str             # common | uncommon | rare


# Foraged-food table, roughly worst -> best. Restore scales with tier.
CATALOG: list[FoodKind] = [
    FoodKind("chum", "Scrap Chum", 10, "common"),
    FoodKind("kelp", "Kelp Wrap", 14, "common"),
    FoodKind("squid", "Circuit Squid", 22, "uncommon"),
    FoodKind("roe", "Neon Roe", 34, "rare"),
    FoodKind("cell", "Power Cell", 45, "rare"),
]
# forage weights parallel CATALOG: commons common, rares rare.
_FORAGE_WEIGHTS = [40, 32, 18, 7, 3]

_BY_ID = {f.id: f for f in CATALOG}


def get(food_id: str) -> FoodKind | None:
    return _BY_ID.get(food_id)


def all_kinds() -> list[FoodKind]:
    return list(CATALOG)


def roll_forage(rng) -> FoodKind:
    """Pick a foraged food from the weighted table. ``rng`` is any object with a
    ``choices`` method (e.g. the stdlib ``random`` module or a seeded Random)."""
    return rng.choices(CATALOG, weights=_FORAGE_WEIGHTS)[0]
