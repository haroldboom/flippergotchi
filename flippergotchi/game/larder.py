"""The Larder: a capped pantry of foraged food, persisted like Wallet/Ledger.

A mirror-store (its own JSON, atomic tmp + os.replace) holding {food_id: count}.
Foraging deposits here when the pet isn't hungry, so a cared-for pet builds a
stockpile to hand-feed later; when genuinely hungry (or the larder is full) the
forage is auto-eaten instead, so neglect play is unchanged. No PetState bump.
"""
from __future__ import annotations

import json
import os


class Larder:
    def __init__(self, path: str, capacity: int = 20):
        self.path = os.path.expanduser(path)
        self.capacity = int(capacity)
        self.items: dict[str, int] = {}
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path) as f:
                raw = json.load(f)
            items = raw.get("items", {}) if isinstance(raw, dict) else {}
            self.items = {str(k): int(v) for k, v in items.items() if int(v) > 0}
        except Exception:
            self.items = {}

    def save(self) -> None:
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = f"{self.path}.tmp.{os.getpid()}"
        with open(tmp, "w") as f:
            json.dump({"items": self.items}, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    def total(self) -> int:
        return sum(self.items.values())

    def is_full(self) -> bool:
        return self.total() >= self.capacity

    def add(self, food_id: str, n: int = 1) -> int:
        """Deposit up to ``n`` of ``food_id``, honouring the capacity. Returns the
        number actually stored (0 if full)."""
        space = max(0, self.capacity - self.total())
        n = min(int(n), space)
        if n > 0:
            self.items[food_id] = self.items.get(food_id, 0) + n
        return n

    def take(self, food_id: str) -> bool:
        """Remove one ``food_id`` if present. Returns True on success."""
        if self.items.get(food_id, 0) > 0:
            self.items[food_id] -= 1
            if self.items[food_id] <= 0:
                del self.items[food_id]
            return True
        return False

    def counts(self) -> dict:
        return dict(self.items)
