"""ASCII animation frames for encounters (net-gun capture, flee, etc.).

On the device these same beats become FlipCTL sprite/HTML frames on the LCD;
here they're ASCII so you can watch the sequence in a terminal or the web view.
A frame is a template string formatted with the monster's fields.
"""
from __future__ import annotations

import time

_AIM = """   .--.              ( ~ ~ )
  ( oo )===O         ( {mon} )
   '--'              ( ~ ~ )
  {name} takes aim with the net-gun..."""

_FIRE = """   .--.    o O o     ( ~ ~ )
  ( oo )--- * * ---> ( {mon} )
   '--'              ( ~ ~ )
  *fwoomp* -- net away!"""

_NET = """   .--.            #=[   ]=#
  ( ^^ )           #( {mon} )#
   '--'            #=[   ]=#
  ...will it hold?"""

_CAUGHT = """  \\(^o^)/          [#######]
                   [ {mon} ]   GOTCHA!
                   [#######]
  {name}'s handshake was netted!"""

_MISS = """   .--.             ~  ~  ~
  ( o_o )          ( {mon} )  ...poof!
   '--'             ~  ~  ~
  {name} broke free -- no handshake."""

_TURN = """        .--.        {mon} >
       ( -_- )         ...
        '--'
  you decide to slip away..."""

_GONE = """   .--.                       > > >
  ( -_- )      *dust*           {mon}
   '--'
  you quietly walked off."""

SEQUENCES = {
    "catch": [_AIM, _FIRE, _NET, _CAUGHT],
    "escape": [_AIM, _FIRE, _MISS],
    "flee": [_TURN, _GONE],
}


def popup(monster) -> str:
    enc = monster.encryption or monster.kind
    return (
        "  +----------------------------------+\n"
        f"  |  A wild {monster.species} appeared!\n"
        f"  |  {monster.name}  Lv{monster.level}  [{enc}]\n"
        "  |\n"
        "  |   [A] CAPTURE          [B] RUN\n"
        "  +----------------------------------+"
    )


def frames(animation: str, monster) -> list:
    mon = monster.species
    return [f.format(mon=mon, name=monster.name) for f in SEQUENCES.get(animation, [])]


def play(frames_list, sink, delay: float = 0.0) -> None:
    """Render each frame via sink(text); pause `delay` between frames."""
    for f in frames_list:
        sink(f)
        if delay:
            time.sleep(delay)
