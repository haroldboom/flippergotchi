"""Enemy-monster sprite lookup.

The WiFi access-point monsters (species chosen by encryption in
``game/monsters.py``) have pixel-art portraits in ``sprites/monsters/`` —
cyberpunk aquatic-mutant villains (jellyfish / crustacean / eel / piranha-boss).
This maps a species name to its sprite so the dex / encounter views can show it.

BLE mini-monsters don't have portraits yet -> ``sprite_path`` returns None for
them, and callers fall back to the ASCII encounter art.
"""
from __future__ import annotations

import base64
import os

_DIR = os.path.join(os.path.dirname(__file__), "sprites", "monsters")

# species (as produced by game.monsters) -> sprite file stem
SPECIES_SPRITES = {
    "Wispling": "wispling",      # open    -- trivial
    "Rustbug": "rustbug",        # wep     -- weak/legacy
    "Wavemon": "wavemon",        # wpa     -- medium
    "Crypterion": "crypterion",  # wpa2    -- boss
}

_cache: dict = {}


def sprite_path(species: str) -> str | None:
    """Absolute path to the species' sprite PNG, or None if there isn't one."""
    stem = SPECIES_SPRITES.get(str(species or ""))
    if not stem:
        return None
    path = os.path.join(_DIR, stem + ".png")
    return path if os.path.exists(path) else None


def sprite_b64(species: str) -> str | None:
    """Base64 of the species sprite (for HTML/data-URI renders), or None."""
    path = sprite_path(species)
    if not path:
        return None
    if path not in _cache:
        with open(path, "rb") as f:
            _cache[path] = base64.b64encode(f.read()).decode()
    return _cache[path]


def modelled_species() -> list:
    """Species that currently have a portrait, in catalogue order."""
    return [s for s in SPECIES_SPRITES if sprite_path(s)]
