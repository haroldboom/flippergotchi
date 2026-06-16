"""The player's collection of captured monsters, persisted to disk."""
from __future__ import annotations

import json
import os

from .monsters import Monster


class Bestiary:
    def __init__(self, path: str):
        self.path = os.path.expanduser(path)
        self.monsters: dict[str, Monster] = {}
        self._load()

    def _load(self) -> None:
        if os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    raw = json.load(f)
                self.monsters = {k: Monster.from_dict(v) for k, v in raw.items()}
            except Exception:
                self.monsters = {}

    def save(self) -> None:
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({k: m.to_dict() for k, m in self.monsters.items()}, f, indent=2)
        os.replace(tmp, self.path)

    def add(self, m: Monster) -> bool:
        """Add or update. Returns True if this monster is newly discovered."""
        existing = self.monsters.get(m.id)
        if existing:
            existing.seen += 1
            existing.signal = m.signal
            existing.clients = max(existing.clients, m.clients)
            existing.captured = existing.captured or m.captured
            return False
        self.monsters[m.id] = m
        return True

    def get(self, name_or_id: str) -> Monster | None:
        if name_or_id in self.monsters:
            return self.monsters[name_or_id]
        for m in self.monsters.values():
            if m.name.lower() == name_or_id.lower():
                return m
        return None

    def all(self) -> list:
        return sorted(self.monsters.values(), key=lambda m: (-m.level, m.name))
