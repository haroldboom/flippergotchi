"""Battle results database: wins / losses / escalations (cloud uploads)."""
from __future__ import annotations

import json
import os
import time

# raw battle() result -> ledger category
_CAT = {"cracked": "win", "failed": "loss", "submitted": "escalate"}


class Ledger:
    def __init__(self, path: str):
        self.path = os.path.expanduser(path)
        self.records: list = []
        self._load()

    def _load(self) -> None:
        if os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    self.records = json.load(f)
            except Exception:
                self.records = []

    def save(self) -> None:
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.records, f, indent=2)
        os.replace(tmp, self.path)

    def record(self, monster, result: str, via: str = "", key: str = "") -> str | None:
        """Log a battle outcome. Returns the category, or None if not counted
        (refused/immune/tamed don't count as a real win/loss)."""
        cat = _CAT.get(result)
        if not cat:
            return None
        self.records.append({
            "id": monster.id, "name": monster.name, "result": cat,
            "raw": result, "via": via, "key": key, "ts": time.time(),
        })
        return cat

    def counts(self) -> dict:
        c = {"win": 0, "loss": 0, "escalate": 0}
        for r in self.records:
            c[r["result"]] = c.get(r["result"], 0) + 1
        return c
