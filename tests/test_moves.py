"""Move set + turn-based duel checks."""
from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flippergotchi.game import moves as moves_mod
from flippergotchi.game import duel as duel_mod
from flippergotchi.game import elements as el


def test_moves_for_returns_element_kit_plus_universals():
    for e in el.ELEMENTS:
        kit = moves_mod.moves_for(e)
        assert len(kit) >= 4
        # element-specific moves are present...
        assert any(m.element == e for m in kit)
        # ...alongside the universal (element-less) moves.
        assert any(m.element == "" for m in kit)


def test_moves_for_unknown_element_is_just_universals():
    kit = moves_mod.moves_for("Mystery")
    assert kit and all(m.element == "" for m in kit)
    assert moves_mod.moves_for(None)  # never empty


def test_move_shape_fields():
    m = moves_mod.moves_for("Spark")[0]
    for attr in ("id", "name", "element", "power", "accuracy", "effect", "chance"):
        assert hasattr(m, attr)


def test_apply_move_respects_type_advantage():
    # Same attacker, same move, same rng seed -> super-effective beats
    # not-very-effective purely from the advantage multiplier.
    you = duel_mod.Fighter("you", level=5, element="Spark")
    them = duel_mod.Fighter("them", level=5, element="Gale")
    move = next(m for m in moves_mod.moves_for("Spark") if m.id == "spark_bolt")

    strong_adv = el.advantage_multiplier("Spark", "Gale")
    weak_adv = el.advantage_multiplier("Spark", "Tide")  # reverse-ish, < 1
    assert strong_adv > 1.0 and weak_adv < 1.0

    r1 = random.Random(42)
    super_eff = moves_mod.apply_move(you, them, move, r1, strong_adv)
    r2 = random.Random(42)
    not_eff = moves_mod.apply_move(you, them, move, r2, weak_adv)

    assert super_eff["hit"] and not_eff["hit"]
    assert super_eff["damage"] > not_eff["damage"]
    assert "super effective" in super_eff["log_line"]


def test_apply_move_can_miss():
    you = duel_mod.Fighter("you", level=5, element="Spark")
    them = duel_mod.Fighter("them", level=5, element="Tide")
    move = moves_mod.Move("flaky", "Flaky", "Spark", 20, 0.5)
    # craft an rng whose first draw forces a miss (> accuracy)
    class _Rng:
        def random(self):
            return 0.99
    out = moves_mod.apply_move(you, them, move, _Rng(), 1.0)
    assert out["hit"] is False and out["damage"] == 0.0
    assert "missed" in out["log_line"]


def test_status_effect_applies_on_proc():
    you = duel_mod.Fighter("you", level=5, element="Spark")
    them = duel_mod.Fighter("them", level=5, element="Gale")
    move = moves_mod.Move("guaranteed", "Guaranteed Stun", "Spark", 10, 1.0, "stun", 1.0)
    # accuracy roll then variance roll then effect roll -- all low -> hit + proc
    class _Rng:
        def __init__(self):
            self.vals = iter([0.0, 0.0, 0.0])
        def random(self):
            return next(self.vals, 0.0)
    out = moves_mod.apply_move(you, them, move, _Rng(), 1.0)
    assert out["hit"] and "stun" in out["effects_applied"]


def test_combatant_dot_ticks_and_stun_skips():
    f = duel_mod.Fighter("t", level=5)
    c = duel_mod._Combatant(f)
    start = c.hp
    c.gain("bleed")
    lines = c.upkeep()
    assert c.hp < start and any("bleed" in ln for ln in lines)

    c.gain("stun")
    assert c.stunned is True

    # shield/buff alter the multipliers the move engine reads
    c.gain("shield")
    assert c.def_mult > 1.0
    c.gain("buff")
    assert c.atk_mult > 1.0


def test_pick_move_is_deterministic_under_seed():
    you = duel_mod.Fighter("you", level=5, element="Tide")
    a = moves_mod.pick_move(you, random.Random(99))
    b = moves_mod.pick_move(you, random.Random(99))
    assert a.id == b.id


def test_full_duel_is_deterministic_and_valid():
    you = duel_mod.Fighter("you", level=8, handshakes=10, gear=5, element="Spark")
    them = duel_mod.Fighter("them", level=8, handshakes=10, element="Gale")

    random.seed(123)
    r1 = duel_mod.duel(you, them)
    random.seed(123)
    r2 = duel_mod.duel(you, them)

    assert r1.you_won == r2.you_won
    assert r1.log == r2.log
    # valid result with a non-trivial blow-by-blow log
    assert isinstance(r1.you_won, bool)
    assert r1.winner in (you.name, them.name)
    assert len(r1.log) > 4
    assert any("uses" in ln or "KO" in ln or "damage" in ln for ln in r1.log)


def test_duel_never_raises_on_garbage():
    you = duel_mod.Fighter("you", level=1, element="???")
    them = duel_mod.Fighter("them", level=1, element=None)
    res = duel_mod.duel(you, them)
    assert res.winner in (you.name, them.name)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all good")
