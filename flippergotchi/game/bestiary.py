"""The player's collection of captured monsters, persisted to disk."""
from __future__ import annotations

import json
import os

from .monsters import Monster, is_valid_id


class Bestiary:
    def __init__(self, path: str):
        self.path = os.path.expanduser(path)
        self.monsters: dict[str, Monster] = {}
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path) as f:
                raw = json.load(f)
        except Exception:
            return
        if not isinstance(raw, dict):
            return
        # tolerant load: parse each row independently so one malformed entry skips
        # only itself instead of wiping the whole collection to empty.
        for k, v in raw.items():
            try:
                self.monsters[k] = Monster.from_dict(v)
            except Exception:
                continue

    def save(self) -> None:
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = f"{self.path}.tmp.{os.getpid()}"
        with open(tmp, "w") as f:
            json.dump({k: m.to_dict() for k, m in self.monsters.items()}, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    def add(self, m: Monster) -> bool:
        """Add or update, keyed strictly by BSSID so two different hidden
        networks stay distinct and the same AP is never duplicated. Returns True
        if this monster is newly discovered."""
        if not is_valid_id(m.id):
            return False
        existing = self.monsters.get(m.id)
        if existing:
            existing.seen += 1
            existing.signal = m.signal
            existing.clients = max(existing.clients, m.clients)
            existing.captured = existing.captured or m.captured
            # carry forward crack/capture state so a re-sighting of an already
            # cracked or captured AP never silently downgrades it.
            existing.defeated = existing.defeated or m.defeated
            existing.key = existing.key or m.key
            if m.capture_path:
                existing.capture_path = m.capture_path
            # shininess is stable per id; preserve it once seen either way
            existing.shiny = existing.shiny or m.shiny
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

    def species_summary(self) -> list[dict]:
        """Group the (still BSSID-keyed, de-duped) entries by SPECIES for a
        collection-style view. Read-only: does not touch on-disk state.

        Returns one dict per distinct species actually caught, each with:
          - ``species``: the species name
          - ``kind``:    "wifi" | "ble" (which realm it belongs to)
          - ``count``:   how many distinct APs/devices of this species are held
          - ``best_level``: the highest level seen among them
          - ``shiny``:   True if any caught individual is a shiny variant
          - ``defeated``: True if any individual has been cracked/tamed

        Sorted by count (desc) then species name, so the fullest collections
        surface first."""
        agg: dict[str, dict] = {}
        for m in self.monsters.values():
            row = agg.get(m.species)
            if row is None:
                agg[m.species] = {
                    "species": m.species,
                    "kind": m.kind,
                    "count": 1,
                    "best_level": m.level,
                    "shiny": bool(getattr(m, "shiny", False)),
                    "defeated": bool(m.defeated),
                }
            else:
                row["count"] += 1
                row["best_level"] = max(row["best_level"], m.level)
                row["shiny"] = row["shiny"] or bool(getattr(m, "shiny", False))
                row["defeated"] = row["defeated"] or bool(m.defeated)
        return sorted(agg.values(), key=lambda r: (-r["count"], r["species"]))
