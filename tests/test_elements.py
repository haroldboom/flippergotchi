"""Elemental type-advantage chart checks."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flippergotchi.game import elements as el


def test_known_strong_pairing_is_above_one():
    assert el.advantage_multiplier("Spark", "Gale") > 1.0
    assert el.matchup_note("Spark", "Gale") == "strong"


def test_reverse_pairing_is_below_one():
    # anti-symmetry: if A beats B, then B is weak vs A
    assert el.advantage_multiplier("Gale", "Spark") < 1.0
    assert el.matchup_note("Gale", "Spark") == "weak"


def test_same_element_is_neutral():
    for e in el.ELEMENTS:
        assert el.advantage_multiplier(e, e) == 1.0
        assert el.matchup_note(e, e) == "neutral"


def test_unknown_or_none_element_is_neutral():
    assert el.advantage_multiplier("Spark", "Mystery") == 1.0
    assert el.advantage_multiplier("Mystery", "Spark") == 1.0
    assert el.advantage_multiplier(None, "Spark") == 1.0
    assert el.advantage_multiplier("Spark", None) == 1.0
    assert el.advantage_multiplier(None, None) == 1.0


def test_multipliers_stay_within_sane_bounds():
    for a in el.ELEMENTS + ["?", None]:
        for d in el.ELEMENTS + ["?", None]:
            m = el.advantage_multiplier(a, d)
            assert 0.5 <= m <= 1.5


def test_aether_is_quirky_not_pure_neutral():
    assert el.advantage_multiplier("Aether", "Spark") > 1.0   # strong vs Spark
    assert el.advantage_multiplier("Aether", "Gale") < 1.0    # weak vs Gale
    assert el.advantage_multiplier("Aether", "Tide") == 1.0   # neutral vs Tide


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all good")
