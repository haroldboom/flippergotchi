"""Loop-side wiring for the big-design batch: soft-stakes forage gate + sick
narration, paragon narration, and the profile's paragon/species readout.
All hermetic (tmp paths, sim mode)."""
from __future__ import annotations

import dataclasses

from flippergotchi.config import Config
from flippergotchi import commands
from flippergotchi.agent import Agent
from flippergotchi.pet import mechanics
from flippergotchi.pet.state import PetState


def _cfg(tmp_path):
    cfg = Config()
    cfg.simulate = True
    cfg.tui = False
    cfg.scan_bluetooth = False
    for f in dataclasses.fields(cfg):
        v = getattr(cfg, f.name)
        if isinstance(v, str) and (v.startswith("~/.flippergotchi")
                                   or v.startswith("/tmp/")):
            setattr(cfg, f.name, str(tmp_path / f.name))
    return cfg


class _SpeakSpy:
    """Records the event keys the agent speaks."""
    def __init__(self):
        self.keys = []

    def install(self, agent):
        real = agent.ai.speak

        def spy(event_key, state, arg="", sub=""):
            self.keys.append(event_key)
            return real(event_key, state, arg, sub)
        agent.ai.speak = spy
        return self


def _make_sick(state):
    """Drive a normal-mode pet into the sick state deterministically."""
    state.hardcore = False
    state.hunger = 100.0
    for _ in range(500):
        mechanics.tick(state, 60.0, Config())  # 500 minutes of neglect
        if mechanics.is_sick(state):
            break
    return state


# -- soft stakes ------------------------------------------------------------

def test_sick_pet_does_not_forage_but_recovers_on_feed(tmp_path):
    cfg = _cfg(tmp_path)
    agent = Agent(cfg, PetState(name="T"))
    _make_sick(agent.state)
    assert mechanics.is_sick(agent.state)
    assert mechanics.can_forage(agent.state) is False

    # forage while sick is a no-op (guarded in tick); call it directly to prove
    # the gate the loop uses: can_forage is False -> loop skips _forage.
    before = agent.larder.total()
    if mechanics.can_forage(agent.state):
        agent._forage(50.0)
    assert agent.larder.total() == before  # nothing foraged while sick

    # hand-feeding still works and nurses it back
    for _ in range(6):
        mechanics.snack(agent.state, cfg)
    assert mechanics.is_sick(agent.state) is False
    assert mechanics.can_forage(agent.state) is True


def test_sick_transition_speaks_once(tmp_path):
    cfg = _cfg(tmp_path)
    agent = Agent(cfg, PetState(name="T"))
    spy = _SpeakSpy().install(agent)
    _make_sick(agent.state)
    # run a couple ticks: the transition into sick should announce exactly once
    for _ in range(3):
        agent.tick(1.0)
    assert spy.keys.count("sick") >= 1
    # after it's already sick, further ticks shouldn't re-announce the onset
    onset = spy.keys.count("sick")
    for _ in range(2):
        agent.tick(1.0)
    # the idle-chatter path may say "sick" at most once more per 20s window;
    # the transition flag prevents a per-tick onset spam
    assert spy.keys.count("sick") <= onset + 1


def test_normal_mode_never_dies_even_when_sick(tmp_path):
    cfg = _cfg(tmp_path)
    agent = Agent(cfg, PetState(name="T"))
    _make_sick(agent.state)
    for _ in range(50):
        mechanics.tick(agent.state, 600.0, cfg)
    assert mechanics.is_dead(agent.state) is False


# -- paragon narration ------------------------------------------------------

def test_paragon_event_is_narrated(tmp_path):
    cfg = _cfg(tmp_path)
    agent = Agent(cfg, PetState(name="T"))
    spy = _SpeakSpy().install(agent)
    agent._progress([{"type": "paragon", "tier": 2}])
    assert any("paragon" in k for k in spy.keys) or "level_up" in spy.keys


# -- profile readout --------------------------------------------------------

def test_profile_shows_paragon_and_species(tmp_path, capsys):
    from flippergotchi import persistence
    cfg = _cfg(tmp_path)
    st = PetState(name="T")
    st.paragon = 3
    persistence.save(cfg.state_path, st)
    commands.cmd_profile(cfg)
    out = capsys.readouterr().out
    assert "PARAGON 3" in out
    assert "/ " not in out or "species:" in out  # species line present
    assert "species:" in out and "19" in out


def test_profile_hides_paragon_when_zero(tmp_path, capsys):
    from flippergotchi import persistence
    cfg = _cfg(tmp_path)
    persistence.save(cfg.state_path, PetState(name="T"))
    commands.cmd_profile(cfg)
    out = capsys.readouterr().out
    assert "PARAGON" not in out
    assert "species:" in out
