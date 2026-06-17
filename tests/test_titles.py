"""Title-selection command: equip an earned title, reject unowned, clear.

Titles are earned through play (achievements append to state.titles); the
`title` command only equips one you already own. These cover the three paths:
owning+selecting sets active_title (persisted), selecting an unowned title is a
no-op + report, and clearing unequips.
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flippergotchi import persistence
from flippergotchi.commands import cmd_title
from flippergotchi.pet.state import PetState


class _Cfg:
    def __init__(self, path):
        self.state_path = path


def _cfg_with(titles, active=""):
    path = os.path.join(tempfile.mkdtemp(), "state.json")
    state = PetState(titles=list(titles), active_title=active)
    persistence.save(path, state)
    return _Cfg(path)


def test_select_owned_title_sets_active():
    cfg = _cfg_with(["Handshake Hunter", "Net Wrangler"])
    cmd_title(cfg, "Net Wrangler")
    assert persistence.load(cfg.state_path).active_title == "Net Wrangler"


def test_select_owned_title_case_insensitive():
    cfg = _cfg_with(["Handshake Hunter"])
    cmd_title(cfg, "handshake hunter")
    # equips the canonical owned spelling, not the user's input
    assert persistence.load(cfg.state_path).active_title == "Handshake Hunter"


def test_select_unowned_title_leaves_active_unchanged(capsys):
    cfg = _cfg_with(["Handshake Hunter"], active="Handshake Hunter")
    cmd_title(cfg, "Legendary Cracker")
    out = capsys.readouterr().out
    assert "haven't earned" in out
    assert persistence.load(cfg.state_path).active_title == "Handshake Hunter"


def test_clear_title():
    cfg = _cfg_with(["Handshake Hunter"], active="Handshake Hunter")
    cmd_title(cfg, "clear")
    assert persistence.load(cfg.state_path).active_title == ""


def test_none_clears_title():
    cfg = _cfg_with(["Handshake Hunter"], active="Handshake Hunter")
    cmd_title(cfg, "none")
    assert persistence.load(cfg.state_path).active_title == ""


def test_list_titles_marks_active(capsys):
    cfg = _cfg_with(["Handshake Hunter", "Net Wrangler"], active="Net Wrangler")
    cmd_title(cfg, None)
    out = capsys.readouterr().out
    assert "Handshake Hunter" in out
    assert "Net Wrangler" in out
    assert "* Net Wrangler" in out


def test_list_no_titles(capsys):
    cfg = _cfg_with([])
    cmd_title(cfg, None)
    assert "No titles earned" in capsys.readouterr().out
