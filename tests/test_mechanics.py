"""Basic mechanics checks: run with `python -m pytest` or `python tests/test_mechanics.py`."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flippergotchi.config import Config
from flippergotchi.pet import mechanics
from flippergotchi.pet.state import PetState


def test_capture_collects_handshake_without_feeding():
    # APs are monsters, not food: catching counts a handshake but does NOT
    # change hunger.
    cfg, s = Config(), PetState(hunger=60.0)
    mechanics.collect(s, "handshake", cfg)
    assert s.handshakes == 1
    assert s.hunger == 60.0


def test_pmkid_capture_counts_pmkid():
    cfg, s = Config(), PetState()
    mechanics.collect(s, "pmkid", cfg)
    assert s.pmkids == 1 and s.handshakes == 0


def test_snack_is_the_food_and_reduces_hunger():
    cfg, s = Config(), PetState(hunger=80.0)
    mechanics.snack(s, cfg)
    assert s.hunger < 80.0
    assert s.handshakes == 0  # foraged food, not a capture


def test_walking_grants_xp_and_can_level_up():
    cfg, s = Config(), PetState()
    ups = mechanics.walk(s, 2000.0, cfg)  # a long walk
    assert s.distance_m == 2000.0
    assert s.level >= 2
    assert any(u["type"] == "level_up" for u in ups)


def test_evolution_stage_tracks_level():
    assert mechanics.stage_for_level(1) == "egg"
    assert mechanics.stage_for_level(8) == "juvenile"
    assert mechanics.stage_for_level(99) == "legend"


def test_mood_thresholds():
    assert mechanics.mood(PetState(hunger=90)) == "hungry"
    assert mechanics.mood(PetState(health=10)) == "sick"
    assert mechanics.mood(PetState(asleep=True)) == "sleeping"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all good")
