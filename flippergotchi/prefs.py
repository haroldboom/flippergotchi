"""Tiny persistent key/value prefs (e.g. 'do not show the battle warning again')."""
from __future__ import annotations

import json
import os


def load(path: str) -> dict:
    path = os.path.expanduser(path)
    if os.path.exists(path):
        try:
            with open(path) as f:
                data = json.load(f)
            # a corrupt/hand-edited non-dict prefs file must degrade to defaults
            # (fail-safe: warnings shown), never crash every consent caller.
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def save(path: str, data: dict) -> None:
    path = os.path.expanduser(path)
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
