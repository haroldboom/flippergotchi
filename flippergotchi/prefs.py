"""Tiny persistent key/value prefs (e.g. 'do not show the battle warning again')."""
from __future__ import annotations

import json
import os


def load(path: str) -> dict:
    path = os.path.expanduser(path)
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save(path: str, data: dict) -> None:
    path = os.path.expanduser(path)
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)
