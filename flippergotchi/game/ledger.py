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
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path) as f:
                raw = json.load(f)
        except Exception:
            return
        # coerce to a list of dict rows: a non-list file (or stray scalar rows)
        # must degrade to empty/skip rather than crash counts()/record() later,
        # which feed achievements / profile / the dex.
        self.records = [r for r in raw if isinstance(r, dict)] if isinstance(raw, list) else []

    def save(self) -> None:
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = f"{self.path}.tmp.{os.getpid()}"
        with open(tmp, "w") as f:
            json.dump(self.records, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
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
            res = r.get("result") if isinstance(r, dict) else None
            if res:
                c[res] = c.get(res, 0) + 1
        return c
