"""Phase-5: hardcore mode, satiety buff, escalating starvation, and the PvP
firewall (satiety touches duels only, never cracking)."""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flippergotchi import persistence
from flippergotchi.config import Config
from flippergotchi.pet import mechanics
from flippergotchi.pet.state import PetState


def _drive(state, cfg, hours, dt_each=600.0):
    """Tick `hours` of decay in `dt_each`-second steps (no feeding)."""
    steps = int(hours * 3600 / dt_each)
    for _ in range(steps):
        mechanics.tick(state, dt_each, cfg)


def test_migrate_v1_petstate_to_v2():
    # a legacy v1 save (no satiety/titles/hardcore) upgrades to a safe Normal pet
    raw = {"name": "Old", "level": 7, "stage": "juvenile", "schema_version": 1}
    merged = persistence.migrate(raw)
    st = PetState.from_dict(merged)
    assert st.schema_version == persistence.CURRENT_SCHEMA == 2
    assert st.hardcore is False and st.satiety == 0.0
    assert st.titles == [] and st.active_title == ""
    assert st.level == 7 and st.stage == "juvenile"      # existing data preserved


def test_eating_banks_satiety_then_decays():
    cfg = Config()
    st = PetState(hunger=80.0, satiety=0.0)
    mechanics.snack(st, cfg)                  # eating banks the well-fed buff
    assert st.satiety > 0
    before = st.satiety
    _drive(st, cfg, hours=4)
    assert st.satiety < before                # ...and it fades over time


def test_normal_mode_floors_health_no_death():
    cfg = Config()
    st = PetState(hunger=100.0, energy=0.0, health=100.0, hardcore=False)
    _drive(st, cfg, hours=48)                 # neglect hard
    assert st.health >= 1.0                   # faints but never dies
    assert mechanics.is_dead(st) is False


def test_hardcore_starves_to_death_and_reborn():
    cfg = Config()
    st = PetState(name="Doomed", element="Cyber", hunger=100.0, energy=0.0,
                  health=100.0, level=12, stage="alpha", hardcore=True)
    _drive(st, cfg, hours=48)
    assert st.health <= 0.0
    assert mechanics.is_dead(st) is True
    egg = mechanics.reborn(st)
    assert egg.level == 1 and egg.stage == "egg"          # progress wiped
    assert egg.name == "Doomed" and egg.hardcore is True  # identity + mode kept
    assert egg.element == "Cyber"


def test_starvation_stage_escalates():
    assert mechanics.starvation_stage(PetState(hunger=10)) == ""
    assert mechanics.starvation_stage(PetState(hunger=78)) == "hungry"
    assert mechanics.starvation_stage(PetState(hunger=95)) == "starving"
    assert mechanics.starvation_stage(PetState(hunger=100)) == "faint"


def test_pvp_firewall_satiety_only_duels_not_cracking():
    import inspect
    from flippergotchi.game import duel as d
    from flippergotchi.game import battle, cracking
    # satiety lifts DUEL power (the one allowed PvP edge)...
    fed = d.Fighter("F", level=5, satiety=100).power()
    starving = d.Fighter("F", level=5, satiety=0).power()
    assert fed > starving
    # ...but cracking takes NO PetState (structural firewall): the signatures can't
    # see hunger/satiety, so they can never influence a crack/battle outcome.
    for fn in (battle.battle, cracking.LocalCracker.crack):
        params = set(inspect.signature(fn).parameters)
        assert not (params & {"state", "hunger", "satiety", "hardcore"})


def test_title_payout_from_gold_capstone():
    from flippergotchi.game import achievements as ach
    from flippergotchi.game.shop import Wallet
    book = ach.AchievementBook(os.path.join(tempfile.mkdtemp(), "a.json"))
    w = Wallet(os.path.join(tempfile.mkdtemp(), "w.json"))
    cfg = Config()
    st = PetState(stage="legend")             # unlocks evolve_to_legend (gold+title)
    ach.grant_reward(book, {"stage": "legend"}, st, cfg, w)
    assert "the Ascended" in st.titles
    assert st.active_title == "the Ascended"  # first earned title auto-equips


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
