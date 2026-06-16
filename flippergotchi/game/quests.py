"""Daily-quests system: a handful of small goals that reroll each day.

Quests track in-game metrics (distance walked, monsters caught, networks
cracked, duels won, snacks foraged). Each day a fresh set of `n` quests is
rolled from a template pool; completing one yields a small reward. Persisted
to JSON exactly like Ledger/Inventory (atomic tmp + os.replace).

Time is never read here: callers pass a `day` string (e.g. "2026-06-16") so
rolling/resetting is deterministic and testable.
"""
from __future__ import annotations

import json
import os
import random
from dataclasses import asdict, dataclass, field

# the only metrics quests may track (must match the names callers record under)
METRICS = ["distance_m", "catches", "cracks", "duel_wins", "snacks"]


@dataclass
class Quest:
    id: str
    description: str
    metric: str
    target: float
    progress: float = 0.0
    done: bool = False
    reward: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Quest":
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in d.items() if k in known})


# template pool: (id, description, metric, target, reward)
_TEMPLATES = [
    ("walk_2k", "Walk 2 km", "distance_m", 2000, {"xp": 50}),
    ("walk_5k", "Walk 5 km", "distance_m", 5000, {"xp": 140}),
    ("catch_5", "Catch 5 monsters", "catches", 5, {"handshakes": 3}),
    ("crack_1", "Crack a network", "cracks", 1, {"xp": 80}),
    ("duel_1", "Win a duel", "duel_wins", 1, {"gear": True}),
    ("forage_3", "Forage 3 snacks", "snacks", 3, {"xp": 30}),
]


def _template_quest(tpl) -> Quest:
    tid, desc, metric, target, reward = tpl
    return Quest(id=tid, description=desc, metric=metric, target=target,
                 reward=dict(reward))


class QuestLog:
    def __init__(self, path: str):
        self.path = os.path.expanduser(path)
        self.day: str = ""
        self.quests: list[Quest] = []
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path) as f:
                raw = json.load(f)
            self.day = raw.get("day", "")
            self.quests = [Quest.from_dict(d) for d in raw.get("quests", [])]
        except Exception:
            self.day, self.quests = "", []

    def save(self) -> None:
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"day": self.day,
                       "quests": [q.to_dict() for q in self.quests]},
                      f, indent=2)
        os.replace(tmp, self.path)

    def roll(self, day: str, n: int = 3, rng=random) -> list:
        """Ensure today's active quests exist. If the stored day differs from
        `day`, pick `n` distinct templates as the new active set (progress
        reset) and record the new day. Deterministic given `rng`."""
        if self.day != day:
            n = max(0, min(n, len(_TEMPLATES)))
            picks = rng.sample(_TEMPLATES, n)
            self.quests = [_template_quest(t) for t in picks]
            self.day = day
        return self.quests

    def record(self, metric: str, amount: float, rng=random) -> list:
        """Bump progress on matching active, not-yet-done quests. Mark a quest
        done when progress >= target. Returns the quests newly completed by
        this call."""
        newly: list = []
        for q in self.quests:
            if q.done or q.metric != metric:
                continue
            q.progress += amount
            if q.progress >= q.target:
                q.done = True
                newly.append(q)
        return newly

    def active(self) -> list:
        return list(self.quests)


def grant_quest_reward(quest, state, inv, cfg) -> str:
    """Apply a completed quest's reward to the player. Kept here (not in the
    pure data classes) so callers don't duplicate the reward logic. Imports are
    local to avoid any package import cycle."""
    from ..pet import mechanics
    from . import equipment

    r = quest.reward or {}
    msgs = []
    if r.get("xp"):
        mechanics.grant_xp(state, r["xp"], cfg)
        msgs.append(f"+{r['xp']} xp")
    if r.get("handshakes"):
        state.handshakes += r["handshakes"]
        msgs.append(f"+{r['handshakes']} handshakes")
    if r.get("gear") and inv is not None:
        it = inv.add(equipment.roll_item(boost=state.level // 2))
        msgs.append(f"gear: {it.name}")
    return ", ".join(msgs) or "no reward"
