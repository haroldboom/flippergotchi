"""HUD polish: the hardcore badge, the severe-starvation danger marker, and the
active-title subtitle on the main flipctl HUD -- plus the agent's escalating,
throttled hardcore-starvation warning emitted BEFORE the pet can die.

All hermetic (tmp paths, sim mode); the renderer only emits HTML (the caller
screenshots+posterizes), so we assert on the markup it writes.
"""
from __future__ import annotations

import dataclasses
import os

from flippergotchi.agent import Agent
from flippergotchi.config import Config
from flippergotchi.pet.state import PetState
from flippergotchi.view import flipctl


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


def _render(tmp_path, state):
    cfg = Config()
    cfg.flipctl_html_out = str(tmp_path / "face.html")
    return open(flipctl.render(state, cfg)).read()


# --- HARDCORE badge --------------------------------------------------------

def test_hardcore_badge_only_when_hardcore(tmp_path):
    normal = _render(tmp_path, PetState(name="Flippy"))
    assert 'class="hc"' not in normal

    hc = _render(tmp_path, PetState(name="Flippy", hardcore=True))
    assert 'class="hc"' in hc
    assert ">HC" in hc  # the corner chip label


# --- STARVING danger marker ------------------------------------------------

def test_starving_marker_only_at_high_hunger(tmp_path):
    # well-fed: no danger marker
    assert "STARVING" not in _render(tmp_path, PetState(name="F", hunger=10.0))
    # merely "hungry" (>=75) is not yet the severe stage -> no marker
    assert "STARVING" not in _render(tmp_path, PetState(name="F", hunger=80.0))
    # "starving" stage (>=90) flashes the marker
    assert "STARVING" in _render(tmp_path, PetState(name="F", hunger=92.0))
    # "faint" stage (>=100) too
    assert "STARVING" in _render(tmp_path, PetState(name="F", hunger=100.0))


def test_starving_marker_independent_of_hardcore(tmp_path):
    # the visual danger marker shows in Normal mode too (it's just a warning)
    assert "STARVING" in _render(tmp_path, PetState(name="F", hunger=95.0,
                                                    hardcore=False))


# --- ACTIVE TITLE subtitle -------------------------------------------------

def test_active_title_only_when_set(tmp_path):
    none = _render(tmp_path, PetState(name="Flippy"))
    assert 'class="sub"' not in none

    titled = _render(tmp_path, PetState(name="Flippy", active_title="Ascended"))
    assert 'class="sub"' in titled
    assert "Ascended" in titled
    # the name + level boxes are untouched
    assert ">Flippy<" in titled and ":L1" in titled


def test_active_title_truncated_to_fit(tmp_path):
    long = "Supreme Overlord of Every Single Handshake In The County"
    html = _render(tmp_path, PetState(name="F", active_title=long))
    # truncated in the markup (CSS ellipsis handles the rest) -- never the full run
    assert long not in html
    assert "Supreme Overlord" in html


def test_active_title_html_escaped(tmp_path):
    html = _render(tmp_path, PetState(name="F", active_title="<b>x</b>"))
    assert "<b>x</b>" not in html
    assert "&lt;b&gt;" in html


# --- agent hardcore starvation warning -------------------------------------

def test_agent_warns_hardcore_starvation(tmp_path):
    cfg = _cfg(tmp_path)
    agent = Agent(cfg, PetState(name="Doomed", hardcore=True, hunger=95.0))
    logs = []
    agent.log = lambda m: logs.append(m)  # capture
    agent._starve_warn_check()
    assert any("[HARDCORE]" in m and "Doomed" in m and "STARVING" in m
               for m in logs)


def test_agent_starvation_warning_is_throttled(tmp_path):
    cfg = _cfg(tmp_path)
    agent = Agent(cfg, PetState(name="Doomed", hardcore=True, hunger=95.0))
    logs = []
    agent.log = lambda m: logs.append(m)
    # many consecutive ticks in the same stage -> not one warning per tick
    for _ in range(20):
        agent._tick_i += 1
        agent._starve_warn_check()
    assert 0 < len(logs) < 20


def test_normal_pet_gets_no_hardcore_warning(tmp_path):
    cfg = _cfg(tmp_path)
    agent = Agent(cfg, PetState(name="Safe", hardcore=False, hunger=100.0))
    logs = []
    agent.log = lambda m: logs.append(m)
    for _ in range(10):
        agent._tick_i += 1
        agent._starve_warn_check()
    assert not logs  # Normal pets never starve to death -> no escalating warning
