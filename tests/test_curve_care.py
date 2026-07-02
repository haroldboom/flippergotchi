"""Growth/care curve fixes:

1. Mid-game evolutions (adult L14, prime L20) fill the old L8->L25 plateau, the
   XP curve is re-tuned gentler (legend in ~4-6 weeks, not ~1.3yr), every stage
   maps to a real sprite, and post-L40 paragon markers accrue without a reset.
2. Soft stakes: a neglected NORMAL-mode pet becomes sick -- stalls XP, can't
   forage, tanks happiness -- then recovers on feeding, and NEVER dies.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flippergotchi.config import Config
from flippergotchi.pet import mechanics
from flippergotchi.pet.state import PetState
from flippergotchi.view import flipctl

_VARIANTS = ["classic", "hammerhead", "goblin", "sawshark", "whaleshark"]
_MOODS = ["", "happy", "hungry", "sleeping", "sick"]


def _cum_xp(level: int, cfg) -> float:
    """Cumulative XP required to *reach* `level` from level 1."""
    return sum(mechanics.xp_to_next(k, cfg) for k in range(1, level))


def _drive(state, cfg, hours, dt_each=600.0):
    steps = int(hours * 3600 / dt_each)
    for _ in range(steps):
        mechanics.tick(state, dt_each, cfg)


# --- FIX 1a: new stages trigger at the right levels -------------------------
def test_new_stages_inserted_between_juvenile_and_alpha():
    names = [s for _, s in mechanics.STAGES]
    assert names == ["egg", "hatchling", "juvenile", "adult", "prime",
                     "alpha", "legend"]


def test_stage_for_level_thresholds():
    assert mechanics.stage_for_level(13) == "juvenile"
    assert mechanics.stage_for_level(14) == "adult"
    assert mechanics.stage_for_level(19) == "adult"
    assert mechanics.stage_for_level(20) == "prime"
    assert mechanics.stage_for_level(24) == "prime"
    assert mechanics.stage_for_level(25) == "alpha"
    assert mechanics.stage_for_level(40) == "legend"
    # unchanged early/late anchors
    assert mechanics.stage_for_level(1) == "egg"
    assert mechanics.stage_for_level(8) == "juvenile"
    assert mechanics.stage_for_level(99) == "legend"


# --- FIX 1a: every stage maps to a real sprite (placeholders included) ------
def test_every_stage_maps_to_a_valid_sprite():
    for _, stage in mechanics.STAGES:
        for variant in _VARIANTS:
            for mood in _MOODS:
                name = flipctl._sprite_for(stage, variant, mood)
                assert flipctl._exists(name), \
                    f"missing sprite {name!r} for {stage}/{variant}/{mood}"


def test_prime_uses_its_own_sprite_family():
    # `prime` now has dedicated (alpha-derived placeholder) art -> resolves to
    # its own sprite family, NOT the alpha one (see tests/test_prime_sprites.py)
    assert flipctl._sprite_for("prime", "classic", "") == "prime"
    assert flipctl._sprite_for("prime", "goblin", "") == "goblin-prime"


# --- FIX 1b: retuned curve hits target cumulative XP, stays monotonic -------
def test_curve_constants_softened():
    cfg = Config()
    assert cfg.level_exp == 1.4          # dropped from 1.6
    assert cfg.base_xp == 120.0


def test_xp_curve_monotonic():
    cfg = Config()
    prev = -1.0
    for lvl in range(1, 60):
        step = mechanics.xp_to_next(lvl, cfg)
        assert step > prev               # per-level cost strictly increases
        prev = step
    # cumulative-to-reach is therefore strictly monotonic across the stage ladder
    cums = [_cum_xp(lvl, cfg) for lvl, _ in mechanics.STAGES]
    assert all(b > a for a, b in zip(cums, cums[1:]))


def test_cumulative_xp_targets():
    cfg = Config()
    # cumulative XP to REACH each stage's first level (sanity ranges)
    assert 5_000 < _cum_xp(8, cfg) < 7_000        # juvenile ~6,277
    assert 20_000 < _cum_xp(14, cfg) < 30_000     # adult    ~25,785
    assert 55_000 < _cum_xp(20, cfg) < 70_000     # prime    ~62,354
    assert 100_000 < _cum_xp(25, cfg) < 115_000   # alpha    ~107,858
    assert 300_000 < _cum_xp(40, cfg) < 380_000   # legend   ~339,437
    # ...and legend is far cheaper than under the old 1.6 curve (~653k)
    old = Config()
    old.level_exp = 1.6
    assert _cum_xp(40, cfg) < 0.6 * _cum_xp(40, old)


# --- FIX 1c: paragon accrues past L40 with NO level reset -------------------
def test_paragon_for_level_math():
    cfg = Config()
    assert mechanics.paragon_for_level(39, cfg) == 0
    assert mechanics.paragon_for_level(40, cfg) == 0
    assert mechanics.paragon_for_level(49, cfg) == 0
    assert mechanics.paragon_for_level(50, cfg) == 1
    assert mechanics.paragon_for_level(60, cfg) == 2
    assert mechanics.paragon_for_level(85, cfg) == 4


def test_update_paragon_never_resets_level():
    cfg = Config()
    st = PetState(level=63)
    tier = mechanics.update_paragon(st, cfg)
    assert tier == 2
    assert mechanics.paragon_tier(st, cfg) == 2
    assert st.level == 63                 # non-destructive: level untouched


def test_levelling_past_40_grants_paragon_without_reset():
    cfg = Config()
    st = PetState(level=49)
    mechanics.update_paragon(st, cfg)     # sync: tier 0 at L49
    assert mechanics.paragon_tier(st, cfg) == 0
    # cross L49 -> L50: banks the first paragon marker, keeps the level
    evts = mechanics.grant_xp(st, mechanics.xp_to_next(49, cfg) + 1, cfg)
    assert st.level == 50
    assert mechanics.paragon_tier(st, cfg) == 1
    assert any(e.get("type") == "paragon" and e.get("tier") == 1 for e in evts)


# --- FIX 2: soft stakes -- non-lethal sickness in normal mode ---------------
def test_healthy_normal_pet_is_not_sick():
    st = PetState(hunger=20.0)
    assert mechanics.is_sick(st) is False
    assert mechanics.can_forage(st) is True


def test_neglect_makes_normal_pet_sick_stalls_xp_and_forage():
    cfg = Config()
    st = PetState(hunger=100.0, health=100.0, happiness=90.0, hardcore=False)
    _drive(st, cfg, hours=12)             # sustained neglect (> sick_onset_hours)

    assert mechanics.is_sick(st) is True
    assert mechanics.can_forage(st) is False
    assert st.happiness <= cfg.sick_happiness_cap   # happiness tanked

    # XP stalls: no source can level a sick pet
    lvl, xp = st.level, st.xp
    assert mechanics.walk(st, 5000.0, cfg) == []
    assert mechanics.collect(st, "handshake", cfg) == [{"type": "caught",
                                                        "kind": "handshake"}]
    assert mechanics.grant_xp(st, 10_000.0, cfg) == []
    assert st.level == lvl and st.xp == xp

    # ...and it never died (normal mode is strictly non-lethal)
    assert st.health >= 1.0
    assert mechanics.is_dead(st) is False


def test_sick_pet_recovers_on_feeding_then_earns_xp_again():
    cfg = Config()
    st = PetState(hunger=100.0, health=100.0, happiness=90.0, hardcore=False)
    _drive(st, cfg, hours=12)
    assert mechanics.is_sick(st) is True

    # feeding is care -> recovers
    for _ in range(10):
        mechanics.snack(st, cfg)
        if not mechanics.is_sick(st):
            break
    assert mechanics.is_sick(st) is False
    assert mechanics.can_forage(st) is True

    # XP flows again once healthy
    lvl, xp = st.level, st.xp
    mechanics.walk(st, 3000.0, cfg)
    assert (st.level, st.xp) != (lvl, xp)


def test_normal_mode_never_dies_even_when_sick_and_starving():
    cfg = Config()
    st = PetState(hunger=100.0, energy=0.0, health=100.0, hardcore=False)
    _drive(st, cfg, hours=72)             # brutal long neglect
    assert mechanics.is_sick(st) is True
    assert st.health >= 1.0
    assert mechanics.is_dead(st) is False


def test_hardcore_is_unaffected_by_sickness():
    cfg = Config()
    st = PetState(hunger=100.0, energy=0.0, health=100.0, hardcore=True)
    _drive(st, cfg, hours=12)
    # NORMAL-mode sickness is disabled in hardcore (it uses starvation-death)
    assert mechanics.is_sick(st) is False
    # ...but a STARVING hardcore pet still can't forage its way out of the death
    # stage -- otherwise a perpetually-walking pet could never starve to death.
    assert mechanics.starvation_stage(st) in ("starving", "faint")
    assert mechanics.can_forage(st) is False
    # a well-fed hardcore pet forages normally.
    assert mechanics.can_forage(PetState(hunger=10.0, health=100.0, hardcore=True)) is True


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all good")
