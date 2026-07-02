"""PvP duel + equipment system checks."""
from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flippergotchi.game import duel as duel_mod
from flippergotchi.game import equipment as eq
from flippergotchi.pet.state import PetState


def test_power_orders_by_level():
    weak = duel_mod.Fighter("a", level=2, handshakes=5)
    strong = duel_mod.Fighter("b", level=12, handshakes=5)
    assert strong.power() > weak.power()


def test_gear_increases_power():
    base = duel_mod.Fighter("a", level=5)
    geared = duel_mod.Fighter("a", level=5, gear=30)
    assert geared.power() == base.power() + 30


def test_win_chance_is_clamped_and_monotonic():
    you = duel_mod.Fighter("you", level=99, handshakes=99, gear=99)
    them = duel_mod.Fighter("them", level=1)
    assert duel_mod.win_chance(you, them) <= 0.92          # upsets stay possible
    assert duel_mod.win_chance(them, you) >= 0.08


def test_higher_level_usually_wins():
    you = duel_mod.Fighter("you", level=15, handshakes=30)
    them = duel_mod.Fighter("them", level=2, handshakes=2)
    random.seed(7)
    wins = sum(duel_mod.duel(you, them).you_won for _ in range(200))
    assert wins > 150


def test_element_advantage_shifts_winrate():
    # equal stats; you hold a strong element (Spark) vs theirs (Gale)
    you = duel_mod.Fighter("you", level=8, handshakes=10, element="Spark")
    them = duel_mod.Fighter("them", level=8, handshakes=10, element="Gale")
    random.seed(3)
    wins = sum(duel_mod.duel(you, them).you_won for _ in range(400))
    assert wins / 400 > 0.55     # the type edge tilts an otherwise even fight


def test_stake_is_bounded_and_transfers():
    you = duel_mod.Fighter("you", level=1, handshakes=0)       # you will lose, no pool
    them = duel_mod.Fighter("them", level=50, handshakes=100)
    st = PetState(handshakes=100)
    random.seed(1)
    res = duel_mod.duel(you, them)
    assert res.stake <= duel_mod.MAX_STAKE
    before = st.handshakes
    duel_mod.apply_result(st, res)
    if res.you_won:
        assert st.handshakes == before + res.stake
    else:
        assert st.handshakes == before - res.stake


def _inv(tmp_file):
    return eq.Inventory(tmp_file("inv.json"))


def test_equip_and_gear_power(tmp_file):
    inv = _inv(tmp_file)
    a = inv.add(eq.Item("i1", "Tuned Helm", "helmet", "rare", 11))
    inv.add(eq.Item("i2", "Scuffed Crest", "fin", "common", 3))
    assert inv.gear_power() == 0          # nothing equipped yet
    inv.equip("i1")
    assert inv.gear_power() == 11 and inv.is_equipped("i1")


def test_pick_forfeit_prefers_weakest_unequipped(tmp_file):
    inv = _inv(tmp_file)
    inv.add(eq.Item("strong", "Mythic Cutlass", "weapon", "legendary", 28))
    weak = inv.add(eq.Item("weak", "Scuffed Monocle", "eyepiece", "common", 3))
    inv.equip("strong")
    assert inv.pick_forfeit().id == weak.id


def test_remove_unequips(tmp_file):
    inv = _inv(tmp_file)
    inv.add(eq.Item("i1", "Tuned Amulet", "amulet", "rare", 11))
    inv.equip("i1")
    inv.remove("i1")
    assert "i1" not in inv.items and inv.gear_power() == 0


def test_inventory_persists(tmp_file):
    p = tmp_file("inv.json")
    inv = eq.Inventory(p)
    inv.add(eq.Item("i1", "Sturdy Helm", "helmet", "uncommon", 6))
    inv.equip("i1")
    inv.save()
    reloaded = eq.Inventory(p)
    assert "i1" in reloaded.items and reloaded.is_equipped("i1")


def test_roll_item_uses_new_slots():
    import random
    random.seed(0)
    slots=set(); stats=set()
    for _ in range(80):
        it=eq.roll_item()
        slots.add(it.slot); stats.add(it.bonus_stat)
        assert it.power>0 and it.bonus_val==it.power
    assert slots <= set(eq.SLOTS) and "weapon" in slots
    assert stats <= {"atk","def","luck"}


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all good")
