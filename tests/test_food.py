"""Food kinds, the Larder pantry, and typed snacks (phase-2 hunger deepening)."""
from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flippergotchi.config import Config
from flippergotchi.game import food
from flippergotchi.game.larder import Larder
from flippergotchi.pet import mechanics
from flippergotchi.pet.state import PetState


def test_food_catalog():
    assert food.get("chum").restore < food.get("roe").restore   # rarer = more
    assert food.get("nope") is None
    assert len(food.all_kinds()) >= 4


def test_roll_forage_deterministic():
    a = food.roll_forage(random.Random(1))
    b = food.roll_forage(random.Random(1))
    assert a.id == b.id                       # same seed -> same pick


def test_larder_add_take_cap(tmp_file):
    lar = Larder(tmp_file("l.json"), capacity=3)
    assert lar.add("chum", 2) == 2
    assert lar.add("kelp", 5) == 1            # only one space left -> capped
    assert lar.is_full()
    assert lar.add("roe") == 0                # full, nothing stored
    assert lar.take("chum") is True
    assert lar.take("nope") is False
    assert lar.total() == 2


def test_larder_persists(tmp_file):
    p = tmp_file("l.json")
    lar = Larder(p, 10)
    lar.add("roe", 3)
    lar.save()
    assert Larder(p, 10).counts() == {"roe": 3}


def test_typed_snack_restore():
    cfg = Config()
    st = PetState(hunger=80.0)
    mechanics.snack(st, cfg)                  # untyped -> cfg.forage_food (12)
    assert st.hunger == 80.0 - cfg.forage_food
    st2 = PetState(hunger=80.0)
    mechanics.snack(st2, cfg, food.get("roe"))   # typed -> roe.restore (34)
    assert st2.hunger == 80.0 - food.get("roe").restore


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
