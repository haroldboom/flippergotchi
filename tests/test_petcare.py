"""Pet-care fantasy: hardcore death runway + memorial, and the sleep/energy
restore loop (Quick wins #8 and #10). See docs/gameplay-review.md."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flippergotchi.config import Config
from flippergotchi.pet import mechanics
from flippergotchi.pet.epitaph import epitaph
from flippergotchi.pet.state import PetState


# --- death runway ----------------------------------------------------------

def test_faint_gives_runway_before_death():
    """At 0 HP the hardcore pet survives a fixed number of faint ticks first."""
    cfg = Config()
    st = PetState(hunger=100.0, energy=0.0, health=0.0, hardcore=True)
    # first faint tick: health is already 0 but death must be held off
    mechanics.tick(st, 600.0, cfg)
    assert st.health <= 0.0
    assert mechanics.is_dead(st) is False        # runway, not a cliff

    # more than one tick of warning before death actually lands
    ticks_alive = 1
    for _ in range(mechanics.FAINT_DEATH_GRACE_TICKS + 2):
        if mechanics.is_dead(st):
            break
        mechanics.tick(st, 600.0, cfg)
        ticks_alive += 1
    assert ticks_alive > 1
    assert mechanics.is_dead(st) is True


def test_runway_is_independent_of_time_scale():
    """A cranked time_scale must not collapse the grace-tick runway."""
    cfg = Config()
    st = PetState(hunger=100.0, energy=0.0, health=0.0, hardcore=True)
    # huge per-tick dt (as if time_scale were enormous) still needs GRACE ticks
    for _ in range(mechanics.FAINT_DEATH_GRACE_TICKS - 1):
        mechanics.tick(st, 999999.0, cfg)
    assert mechanics.is_dead(st) is False
    mechanics.tick(st, 999999.0, cfg)
    assert mechanics.is_dead(st) is True


def test_recovery_resets_the_runway():
    """Feeding out of the faint stage refills the grace runway."""
    cfg = Config()
    st = PetState(hunger=100.0, energy=0.0, health=0.0, hardcore=True)
    for _ in range(mechanics.FAINT_DEATH_GRACE_TICKS - 1):
        mechanics.tick(st, 600.0, cfg)
    st.hunger = 20.0                              # rescued out of faint
    mechanics.tick(st, 600.0, cfg)
    assert getattr(st, "_faint_ticks", 0) == 0


def test_normal_mode_still_cannot_die():
    cfg = Config()
    st = PetState(hunger=100.0, energy=0.0, health=100.0, hardcore=False)
    for _ in range(300):
        mechanics.tick(st, 600.0, cfg)
    assert st.health >= 1.0
    assert mechanics.is_dead(st) is False


# --- epitaph ---------------------------------------------------------------

def test_epitaph_includes_name_level_and_catches():
    st = PetState(name="Doomed", level=12, stage="alpha", handshakes=7, pmkids=3)
    text = epitaph(st)
    assert "Doomed" in text
    assert "12" in text                           # level
    assert "10" in text                           # 7 handshakes + 3 pmkids


def test_epitaph_lifetime_catches_override():
    st = PetState(name="Rex", handshakes=1, pmkids=1)
    assert "42" in epitaph(st, lifetime_catches=42)


def test_epitaph_never_raises_on_bare_state():
    # even a default/partial state produces a string, no exceptions
    assert isinstance(epitaph(PetState()), str)
    assert isinstance(epitaph(PetState(), lifetime_catches=None), str)


# --- sleep / energy --------------------------------------------------------

def test_maybe_sleep_sleeps_when_tired_and_restores_energy():
    cfg = Config()
    st = PetState(energy=5.0, asleep=False)
    assert mechanics.maybe_sleep(st, cfg) is True
    assert st.asleep is True
    before = st.energy
    mechanics.tick(st, 600.0, cfg)                # sleeping restores energy
    assert st.energy > before


def test_maybe_sleep_wakes_when_rested():
    cfg = Config()
    st = PetState(energy=95.0, asleep=True)
    assert mechanics.maybe_sleep(st, cfg) is False
    assert st.asleep is False


def test_maybe_sleep_stays_awake_when_energetic():
    cfg = Config()
    st = PetState(energy=90.0, asleep=False)
    assert mechanics.maybe_sleep(st, cfg) is False
    assert st.asleep is False


def test_maybe_sleep_survives_broken_cfg():
    class Bad:
        sleep_energy_low = 50.0
        wake_energy_high = 10.0                    # inverted / nonsense
    st = PetState(energy=5.0, asleep=False)
    assert mechanics.maybe_sleep(st, Bad()) is True
    st.energy = 100.0
    assert mechanics.maybe_sleep(st, Bad()) is False


def test_sleeping_face_becomes_reachable():
    """Full loop: tired pet sleeps, energy climbs back via ticks, mood shows it."""
    cfg = Config()
    st = PetState(energy=5.0, asleep=False)
    mechanics.maybe_sleep(st, cfg)
    assert mechanics.mood(st) == "sleeping"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
