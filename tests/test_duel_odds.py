"""R4: pre-fight duel odds display derives from the ACTUAL resolver.

`estimate_win_pct` Monte-Carlos the real turn engine (`_run_duel`) on a local
seeded RNG so `cmd_duel`'s "~X% to win" line matches what the fight will do
(gear ATK/DEF/LUCK, element multipliers, the clamped HP-share roll) -- unlike
the old `win_chance` power-ratio guess, which is kept only for the agent's
cheap auto-duel gate.
"""
from __future__ import annotations

import copy
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flippergotchi.game import duel as duel_mod


def _strong():
    return duel_mod.Fighter("strong", level=40, handshakes=80, gear=120,
                            atk=60, defense=60, luck=40, element="Spark")


def _weak():
    return duel_mod.Fighter("weak", level=2, handshakes=3, element="Gale")


def test_deterministic_per_seed():
    you, them = _strong(), _weak()
    a = duel_mod.estimate_win_pct(you, them, seed=0)
    b = duel_mod.estimate_win_pct(you, them, seed=0)
    assert a == b                       # same (you, them, seed) -> same number
    c = duel_mod.estimate_win_pct(you, them, seed=1)
    d = duel_mod.estimate_win_pct(you, them, seed=1)
    assert c == d
    # different seeds are allowed to differ, but only by sampling noise
    assert abs(a - c) < 0.15


def test_favorite_above_half_underdog_below():
    assert duel_mod.estimate_win_pct(_strong(), _weak()) > 0.5
    assert duel_mod.estimate_win_pct(_weak(), _strong()) < 0.5


def test_bounds_and_realistic_band_on_extreme_mismatch():
    fav = duel_mod.estimate_win_pct(_strong(), _weak())
    dog = duel_mod.estimate_win_pct(_weak(), _strong())
    for p in (fav, dog):
        assert 0.0 < p < 1.0
    # UPSET_FLOOR clamps every per-fight roll to [0.05, 0.95]; the Monte-Carlo
    # average must respect that band up to sampling noise (n=201 default).
    assert 0.03 <= dog <= 0.5
    assert 0.5 <= fav <= 0.97


def test_does_not_perturb_global_random_state():
    random.seed(424242)
    before = random.getstate()
    duel_mod.estimate_win_pct(_strong(), _weak(), seed=3)
    assert random.getstate() == before
    # and the next global draw is exactly what it would have been anyway
    expected = random.Random()
    expected.seed(424242)
    assert random.random() == expected.random()


def test_does_not_mutate_fighters():
    you, them = _strong(), _weak()
    y0, t0 = copy.deepcopy(you), copy.deepcopy(them)
    duel_mod.estimate_win_pct(you, them)
    assert you == y0 and them == t0


def test_tracks_resolver_better_than_win_chance_on_geared_mismatch():
    """Equal base power, but 'you' bring gear stats + the element edge --
    exactly what win_chance() is blind to (it reads power() only). The
    estimate must sit much closer to the resolver's empirical win rate."""
    you = duel_mod.Fighter("you", level=8, handshakes=20,
                           atk=90, defense=90, luck=60, element="Spark")
    them = duel_mod.Fighter("them", level=8, handshakes=20, element="Gale")

    wc = duel_mod.win_chance(you, them)
    assert wc == 0.5                     # power ratio sees a coin flip

    est = duel_mod.estimate_win_pct(you, them, n=401)

    rng = random.Random(1234)            # empirical truth from the real engine
    trials = 600
    emp = sum(duel_mod.duel(you, them, rng=rng).you_won
              for _ in range(trials)) / trials

    assert emp > 0.5                     # the geared side really is favored
    assert est > 0.5                     # ...and the display now says so
    assert abs(est - emp) < abs(wc - emp)
    assert abs(est - emp) < 0.10         # genuinely close, not just less wrong
