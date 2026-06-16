from __future__ import annotations

import json
import os

from .pet.state import PetState


def load(path: str) -> PetState:
    path = os.path.expanduser(path)
    if os.path.exists(path):
        try:
            with open(path) as f:
                return PetState.from_dict(json.load(f))
        except Exception:
            pass
    return PetState()


def save(path: str, state: PetState) -> None:
    path = os.path.expanduser(path)
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state.to_dict(), f, indent=2)
    os.replace(tmp, path)
