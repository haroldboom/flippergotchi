from __future__ import annotations

import os

from ..pet import mechanics
from .faces import face


def _bar(value: float, width: int = 12) -> str:
    n = int(round(max(0.0, min(100.0, value)) / 100 * width))
    return "#" * n + "." * (width - n)


def render(state, cfg, line: str = "", mood_override: str | None = None):
    m = mood_override or mechanics.mood(state)
    nxt = mechanics.xp_to_next(state.level, cfg)
    os.system("clear")
    print(face(m))
    print(f"  {state.name}   Lv.{state.level} [{state.stage}]   mood: {m}")
    print()
    print(f"  food    {_bar(100 - state.hunger)}  {100 - state.hunger:5.1f}")
    print(f"  energy  {_bar(state.energy)}  {state.energy:5.1f}")
    print(f"  health  {_bar(state.health)}  {state.health:5.1f}")
    print(f"  happy   {_bar(state.happiness)}  {state.happiness:5.1f}")
    print(f"  xp      {_bar(state.xp / nxt * 100)}  {state.xp:.0f}/{nxt:.0f}")
    print()
    print(f"  caught {state.handshakes} handshakes + {state.pmkids} pmkids   "
          f"walked {state.distance_m:.0f} m")
    if line:
        print()
        print(f'  ({state.name}) "{line}"')
