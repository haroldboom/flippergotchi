"""Achievements: persistent badges unlocked by crossing lifetime milestones.

A badge has an id, name, description, a tracked `metric` and a `threshold`. When
the player's running stats reach/exceed a threshold the badge unlocks once (and
never re-grants). Each unlock can carry a small reward (scrap currency and/or
food) which `check()` returns so the caller applies it — this module never
mutates pet/wallet state itself, mirroring quests.grant_quest_reward's split.

Persisted to JSON exactly like Ledger/QuestLog/Inventory (atomic tmp +
os.replace). The set of unlocked badge ids is all we store.

Stats are supplied by the caller as a flat dict, e.g.::

    {"catches": 12, "cracks": 3, "duel_wins": 6, "distance_m": 11000,
     "level": 7, "stage": "legend", "equipped_slots": 5, "shinies": 1}

Achievements observe game progress only; nothing here influences WiFi cracking.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

# slot count that counts as a "full loadout" (mirrors equipment.SLOTS length)
FULL_LOADOUT_SLOTS = 5


@dataclass
class Badge:
    id: str
    name: str
    description: str
    metric: str            # key looked up in the stats dict
    threshold: float       # unlock when stats[metric] >= threshold
    reward: dict = field(default_factory=dict)   # {"scrap": int, "food": int}

    def met(self, stats: dict) -> bool:
        return _stat_value(stats, self.metric) >= self.threshold


def _stat_value(stats: dict, metric: str) -> float:
    """Read a metric from the stats dict, coercing booleans/strings sensibly.

    A couple of metrics are categorical milestones rather than counters:
      * ``stage_legend`` -> 1 when stats['stage'] is a legendary stage.
    Everything else is a numeric count (missing => 0)."""
    if metric == "stage_legend":
        stage = str(stats.get("stage", "")).lower()
        return 1.0 if stage in ("legend", "legendary") else 0.0
    v = stats.get(metric, 0)
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# The badge catalogue. Rewards stay small so achievements supplement, not
# replace, the core economy.
CATALOG: list[Badge] = [
    Badge("first_catch", "First Blood", "Catch your first monster",
          "catches", 1, {"scrap": 50}),
    Badge("catch_10", "Beastmaster I", "Catch 10 monsters",
          "catches", 10, {"scrap": 100}),
    Badge("catch_50", "Beastmaster II", "Catch 50 monsters",
          "catches", 50, {"scrap": 300}),
    Badge("catch_100", "Beastmaster III", "Catch 100 monsters",
          "catches", 100, {"scrap": 600, "food": 5}),
    Badge("crack_1", "Lockpicker", "Crack your first network",
          "cracks", 1, {"scrap": 80}),
    Badge("crack_10", "Safecracker", "Crack 10 networks",
          "cracks", 10, {"scrap": 250}),
    Badge("duel_win_5", "Brawler", "Win 5 duels",
          "duel_wins", 5, {"scrap": 120}),
    Badge("duel_win_25", "Gladiator", "Win 25 duels",
          "duel_wins", 25, {"scrap": 400, "food": 3}),
    Badge("walk_10k_m", "Trailblazer", "Walk 10 km total",
          "distance_m", 10000, {"scrap": 150}),
    Badge("walk_50k_m", "Marathoner", "Walk 50 km total",
          "distance_m", 50000, {"scrap": 500, "food": 5}),
    Badge("level_10", "Seasoned", "Reach level 10",
          "level", 10, {"scrap": 200}),
    Badge("evolve_to_legend", "Ascended", "Evolve into a legendary form",
          "stage_legend", 1, {"scrap": 500, "food": 5}),
    Badge("full_loadout", "Geared Up", "Equip all 5 gear slots at once",
          "equipped_slots", FULL_LOADOUT_SLOTS, {"scrap": 180}),
    Badge("shiny_find", "Sparkle", "Find a shiny monster",
          "shinies", 1, {"scrap": 300, "food": 3}),
]

_BY_ID = {b.id: b for b in CATALOG}


def get(badge_id: str) -> Badge | None:
    return _BY_ID.get(badge_id)


class AchievementBook:
    def __init__(self, path: str):
        self.path = os.path.expanduser(path)
        self._unlocked: set[str] = set()
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path) as f:
                raw = json.load(f)
            ids = raw.get("unlocked", []) if isinstance(raw, dict) else raw
            self._unlocked = {i for i in ids if i in _BY_ID}
        except Exception:
            self._unlocked = set()

    def save(self) -> None:
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"unlocked": sorted(self._unlocked)}, f, indent=2)
        os.replace(tmp, self.path)

    def is_unlocked(self, badge_id: str) -> bool:
        return badge_id in self._unlocked

    def check(self, stats: dict) -> list[Badge]:
        """Unlock any badges whose threshold the stats now meet (and that aren't
        already unlocked). Returns the list of NEWLY unlocked badges; the caller
        applies each badge's `reward`. Idempotent: re-checking with the same or
        higher stats grants nothing new."""
        newly: list[Badge] = []
        for b in CATALOG:
            if b.id in self._unlocked:
                continue
            if b.met(stats):
                self._unlocked.add(b.id)
                newly.append(b)
        return newly

    def unlocked(self) -> list[Badge]:
        """Unlocked badges, in catalogue order."""
        return [b for b in CATALOG if b.id in self._unlocked]

    def locked(self) -> list[Badge]:
        return [b for b in CATALOG if b.id not in self._unlocked]

    def all(self) -> list[Badge]:
        """Full catalogue (unlocked or not)."""
        return list(CATALOG)

    def progress(self) -> tuple[int, int]:
        """(unlocked_count, total_count)."""
        return len(self._unlocked), len(CATALOG)
