"""Combat-depth reconnection checks: gear stats, SET BONUSES and ELEMENT now
actually change duel outcomes (they used to be UI decoration the resolver
never read). See docs/gameplay-review.md, "Combat & Systems Depth".
"""
from __future__ import annotations

import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flippergotchi.game import duel as duel_mod
from flippergotchi.game import elements as el
from flippergotchi.game import equipment as eq
from flippergotchi.pet.state import PetState

N = 400  # Monte Carlo sample per win-rate comparison


def _inv() -> eq.Inventory:
    return eq.Inventory(os.path.join(tempfile.mkdtemp(), "inv.json"))


def _full_kit(inv: eq.Inventory, set_tag: str = "", power: int = 18) -> None:
    """Add + equip one item per slot, optionally all tagged into one set."""
    for i, slot in enumerate(eq.SLOTS):
        it = eq.Item(f"k{i}", f"Piece {slot}", slot, "epic", power,
                     bonus_stat=eq._SLOT_STAT[slot], bonus_val=power,
                     set=set_tag)
        inv.add(it)
        inv.equip(it.id)


def _winrate(you: duel_mod.Fighter, them: duel_mod.Fighter, seed: int = 11) -> float:
    rng = random.Random(seed)
    return sum(duel_mod.duel(you, them, rng=rng).you_won for _ in range(N)) / N


# ---------------------------------------------------------------------------
# 1. gear stats + pvp_power are actually read by the resolver
# ---------------------------------------------------------------------------

def test_fighter_from_pet_uses_pvp_power_and_stat_totals():
    inv = _inv()
    _full_kit(inv, set_tag="Apex Predator")
    state = PetState(name="Flippy", level=8, handshakes=10, element="Tide")
    f = duel_mod.fighter_from_pet(state, inv)
    # power base is pvp_power (gear + set power bonus), NOT raw gear_power
    assert inv.pvp_power() > inv.gear_power()
    assert f.gear == inv.pvp_power()
    # per-stat totals (item rolls + set stat bonuses) seed the fighter
    stats = inv.stat_totals()
    assert (f.atk, f.defense, f.luck) == (stats["atk"], stats["def"], stats["luck"])
    assert f.atk > 0 and f.defense > 0 and f.luck > 0
    # element comes from the pet, not a hardcoded Aether
    assert f.element == "Tide"


def test_gear_stats_change_duel_outcomes():
    """A fully geared fighter beats its ungeared twin way more than half the time."""
    inv = _inv()
    _full_kit(inv, set_tag="Apex Predator")
    state = PetState(name="Geared", level=8, handshakes=10)
    geared = duel_mod.fighter_from_pet(state, inv)
    naked = duel_mod.Fighter("Naked", level=8, handshakes=10)
    assert _winrate(geared, naked) > 0.70


# ---------------------------------------------------------------------------
# 2. completing a gear set matters (same items, only the set tag differs)
# ---------------------------------------------------------------------------

def test_completed_set_wins_more_than_untagged_same_gear():
    set_inv, plain_inv = _inv(), _inv()
    _full_kit(set_inv, set_tag="Apex Predator")
    _full_kit(plain_inv, set_tag="")   # identical pieces, no set

    st = PetState(name="you", level=8, handshakes=10)
    with_set = duel_mod.fighter_from_pet(st, set_inv)
    without = duel_mod.fighter_from_pet(st, plain_inv)
    # same rival for both
    rival_inv = _inv()
    _full_kit(rival_inv, set_tag="")
    rival = duel_mod.fighter_from_pet(PetState(name="rival", level=8, handshakes=10),
                                      rival_inv)

    wr_set = _winrate(with_set, rival, seed=21)
    wr_plain = _winrate(without, rival, seed=21)
    # the mirror match sits ~50%; the 5-pc set bonus must tilt it clearly
    assert 0.40 < wr_plain < 0.60
    assert wr_set > wr_plain + 0.05


# ---------------------------------------------------------------------------
# 3. ATK-heavy vs DEF-heavy loadouts behave differently
# ---------------------------------------------------------------------------

def test_atk_and_def_loadouts_seed_different_multipliers():
    atk_f = duel_mod.Fighter("atk", level=8, atk=50.0)
    def_f = duel_mod.Fighter("def", level=8, defense=50.0)
    plain = duel_mod.Fighter("plain", level=8)
    ca, cd, cp = (duel_mod._Combatant(f) for f in (atk_f, def_f, plain))
    assert ca.atk_mult > cp.atk_mult and ca.def_mult == cp.def_mult
    assert cd.def_mult > cp.def_mult and cd.atk_mult == cp.atk_mult


def test_luck_seeds_crit_and_crits_can_land():
    lucky = duel_mod._Combatant(duel_mod.Fighter("lucky", level=8, luck=60.0))
    plain = duel_mod._Combatant(duel_mod.Fighter("plain", level=8))
    assert lucky.crit_chance > 0 == plain.crit_chance
    # a high-luck fighter's log eventually shows a CRIT
    you = duel_mod.Fighter("lucky", level=8, handshakes=10, luck=60.0)
    them = duel_mod.Fighter("them", level=8, handshakes=10)
    rng = random.Random(4)
    assert any("CRIT!" in ln
               for _ in range(30)
               for ln in duel_mod.duel(you, them, rng=rng).log)


def test_stat_loadouts_beat_statless_twin():
    atk_f = duel_mod.Fighter("atk", level=8, handshakes=10, atk=50.0)
    def_f = duel_mod.Fighter("def", level=8, handshakes=10, defense=50.0)
    plain = duel_mod.Fighter("plain", level=8, handshakes=10)
    assert _winrate(atk_f, plain, seed=31) > 0.60
    assert _winrate(def_f, plain, seed=32) > 0.60


# ---------------------------------------------------------------------------
# 4. element flows from PetState/param into the resolver and swings win-rate
# ---------------------------------------------------------------------------

def test_element_param_overrides_and_is_normalised():
    st = PetState(name="you", element="Aether")
    f = duel_mod.fighter_from_pet(st, None, element="spark")   # alias, lowercase
    assert f.element == "Spark"
    f2 = duel_mod.fighter_from_pet(st, None)                    # falls back to state
    assert f2.element == "Aether"


def test_element_advantage_swings_winrate_both_ways():
    st = PetState(name="you", level=8, handshakes=10)
    rival = {"name": "rival", "addr": "aa", "level": 8, "handshakes": 10,
             "gear_power": 0, "element": "Gale"}
    strong = duel_mod.fighter_from_pet(st, None, element="Spark")  # Spark > Gale
    weak = duel_mod.fighter_from_pet(st, None, element="Tide")     # Tide < Gale
    them = duel_mod.fighter_from_peer(rival)
    wr_strong = _winrate(strong, them, seed=41)
    wr_weak = _winrate(weak, them, seed=41)
    assert wr_strong > 0.55            # advantage lifts you above even
    assert wr_weak < 0.45              # disadvantage drops you below even
    assert wr_strong - wr_weak > 0.15  # the chart is a real lever


def test_element_persists_through_state_roundtrip():
    st = PetState(name="you")
    assert st.element == "Aether"          # default unchanged
    assert st.set_element("gale") is True
    assert st.element == "Gale"
    assert st.set_element("plasma") is False   # unknown -> rejected, unchanged
    assert st.element == "Gale"
    st2 = PetState.from_dict(st.to_dict())
    assert st2.element == "Gale"
    # and the round-tripped state builds a fighter with that element
    assert duel_mod.fighter_from_pet(st2, None).element == "Gale"


def test_normalize_accepts_bands_and_rejects_junk():
    assert el.normalize("2.4GHz") == "Spark"
    assert el.normalize("BLE") == "Aether"
    assert el.normalize("TIDE") == "Tide"
    assert el.normalize("wat") is None and el.normalize(None) is None


# ---------------------------------------------------------------------------
# 5. best_loadout: auto-equip best-in-slot, set-aware
# ---------------------------------------------------------------------------

def test_best_loadout_picks_strongest_per_slot():
    inv = _inv()
    inv.add(eq.Item("h1", "Scuffed Helm", "helmet", "common", 3, "def", 3))
    inv.add(eq.Item("h2", "Mythic Helm", "helmet", "legendary", 28, "def", 28))
    inv.add(eq.Item("w1", "Tuned Shiv", "weapon", "rare", 11, "atk", 11))
    lo = inv.best_loadout()
    assert lo["helmet"].id == "h2" and lo["weapon"].id == "w1"
    assert inv.equipped == {"helmet": "h2", "weapon": "w1"}
    assert inv.gear_power() == 39


def test_best_loadout_prefers_completing_a_set_when_it_scores_higher():
    inv = _inv()
    # 5 matched Apex pieces at power 18...
    for i, slot in enumerate(eq.SLOTS):
        inv.add(eq.Item(f"s{i}", f"Apex {slot}", slot, "epic", 18,
                        eq._SLOT_STAT[slot], 18, set="Apex Predator"))
    # ...plus one slightly stronger off-set helmet (20 < 18 + 5pc bonus value)
    inv.add(eq.Item("off", "Loner Helm", "helmet", "epic", 20, "def", 20))
    lo = inv.best_loadout()
    assert lo["helmet"].set == "Apex Predator"     # completes the 5-pc set
    assert len(lo) == 5
    assert inv.set_bonus()["power"] > 0


def test_best_loadout_takes_offset_piece_when_set_bonus_is_worth_less():
    inv = _inv()
    # only 2 set pieces (weak 2-pc tier) vs a vastly stronger off-set weapon
    inv.add(eq.Item("s1", "Static Shiv", "weapon", "common", 3, "atk", 3,
                    set="Static Coil"))
    inv.add(eq.Item("s2", "Static Charm", "amulet", "common", 3, "luck", 3,
                    set="Static Coil"))
    inv.add(eq.Item("big", "Mythic Cutlass", "weapon", "legendary", 28, "atk", 28))
    lo = inv.best_loadout()
    assert lo["weapon"].id == "big"


def test_best_loadout_empty_bag_is_a_noop():
    inv = _inv()
    assert inv.best_loadout() == {}
    assert inv.equipped == {}


# ---------------------------------------------------------------------------
# 6. auto_resolve: the loop-callable seam settles everything
# ---------------------------------------------------------------------------

def _peer(**over) -> dict:
    p = {"name": "Rival", "addr": "aa:bb", "level": 2, "handshakes": 20,
         "gear_power": 0, "element": "Gale"}
    p.update(over)
    return p


def test_auto_resolve_win_settles_stake_loot_and_wins():
    inv = _inv()
    _full_kit(inv, set_tag="Apex Predator")
    st = PetState(name="Flippy", level=15, handshakes=30, element="Spark")
    peer = _peer()   # Lv2 Gale peer: Spark advantage + huge gear = near-lock
    out = duel_mod.auto_resolve(st, peer, inv, rng=random.Random(7))
    assert out.you_won and out.winner == "Flippy" and out.loser == "Rival"
    assert out.stake > 0
    assert st.handshakes == 30 + out.stake          # stake credited
    assert peer["handshakes"] == 20 - out.stake     # peer pool drained
    assert st.duel_wins == 1
    assert out.loot is not None and out.loot.id in inv.items
    assert out.forfeit is None
    assert "WON" in out.summary and "Rival" in out.summary
    assert len(out.result.log) > 3                  # narratable blow-by-blow


def test_auto_resolve_loss_forfeits_gear():
    inv = _inv()
    it = inv.add(eq.Item("only", "Scuffed Monocle", "eyepiece", "common", 3,
                         "luck", 3))
    st = PetState(name="Flippy", level=1, handshakes=5, element="Tide")
    peer = _peer(level=40, handshakes=50, gear_power=35, element="Gale")
    # find a losing seed (losses are overwhelmingly likely; never assume seed 0)
    for seed in range(50):
        inv2 = _inv()
        inv2.add(eq.Item("only", it.name, it.slot, it.rarity, it.power,
                         it.bonus_stat, it.bonus_val))
        st2 = PetState(name="Flippy", level=1, handshakes=5, element="Tide")
        peer2 = _peer(level=40, handshakes=50, gear_power=35, element="Gale")
        out = duel_mod.auto_resolve(st2, peer2, inv2, rng=random.Random(seed))
        if not out.you_won:
            assert out.forfeit is not None and "only" not in inv2.items
            assert out.loot is None
            assert st2.handshakes == 5 - out.stake
            assert "LOST" in out.summary
            return
    raise AssertionError("Lv1 vs Lv40 never lost in 50 seeds -- resolver broken")


def test_auto_resolve_element_param_beats_hardcoded_default():
    """The element argument is honoured: same pet, different element, the
    matchup note in the duel log follows the parameter."""
    st = PetState(name="Flippy", level=8, handshakes=10)   # element Aether
    peer = _peer(level=8, handshakes=10, element="Gale")
    out = duel_mod.auto_resolve(st, peer, None, element="Spark",
                                rng=random.Random(3))
    assert "Spark" in out.result.log[0]
    assert any("strong for you" in ln for ln in out.result.log)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all good")
