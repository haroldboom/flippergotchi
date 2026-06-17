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

# the only metrics quests may track (must match the names callers record under).
# Every metric here MUST have a record() call site, or it is dead content:
#   distance_m/catches/cracks/snacks (agent), duel_wins (duel cmd),
#   tames (agent._tame_ble), legendary_kills (agent._field_battle, WEP/WPA1).
METRICS = ["distance_m", "catches", "cracks", "duel_wins", "snacks",
           "tames", "legendary_kills"]

# persisted-file schema version for QuestLog (v2 adds the weekly + bonus blocks).
CURRENT_SCHEMA = 2
# one-time scrap for clearing every daily in a day (the "finish the set" nudge).
DAILY_CLEAR_BONUS = 80


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


# DAILY template pool: (id, description, metric, target, reward). Scrap is tuned
# so a full clear of `n` dailies + the all-clear bonus lands near ~150/day.
_TEMPLATES = [
    ("walk_2k", "Walk 2 km", "distance_m", 2000, {"xp": 50, "scrap": 30}),
    ("walk_5k", "Walk 5 km", "distance_m", 5000, {"xp": 140, "scrap": 55}),
    ("catch_5", "Catch 5 monsters", "catches", 5, {"handshakes": 3, "scrap": 40}),
    ("crack_1", "Crack a network", "cracks", 1, {"xp": 80, "scrap": 55}),
    ("duel_1", "Win a duel", "duel_wins", 1, {"gear": True, "scrap": 40}),
    ("forage_3", "Forage 3 snacks", "snacks", 3, {"xp": 30, "scrap": 25}),
    ("tame_2", "Tame 2 Bluetooth devices", "tames", 2, {"xp": 40, "scrap": 35}),
    ("legend_1", "Crack a WEP/WPA1 legendary", "legendary_kills", 1, {"scrap": 60}),
]
# roll weights: common everyday goals show often, rare ones (legendaries) rarely.
_TEMPLATE_WEIGHT = {
    "walk_2k": 10, "walk_5k": 6, "catch_5": 10, "crack_1": 8,
    "duel_1": 5, "forage_3": 8, "tame_2": 6, "legend_1": 3,
}

# WEEKLY template pool: bigger targets, one-time-per-week payouts that sit ABOVE
# the daily-sum so dailies stay the primary loop (see economy notes).
_WEEKLY_TEMPLATES = [
    ("w_walk", "Walk 20 km this week", "distance_m", 20000, {"scrap": 120, "food": 3}),
    ("w_catch", "Catch 30 monsters", "catches", 30, {"scrap": 120}),
    ("w_crack", "Crack 8 networks", "cracks", 8, {"scrap": 150, "gear": True}),
    ("w_duel", "Win 6 duels", "duel_wins", 6, {"scrap": 120}),
    ("w_tame", "Tame 12 Bluetooth devices", "tames", 12, {"scrap": 100, "food": 3}),
]


def _template_quest(tpl) -> Quest:
    tid, desc, metric, target, reward = tpl
    return Quest(id=tid, description=desc, metric=metric, target=target,
                 reward=dict(reward))


def _weighted_distinct(templates, n: int, rng) -> list:
    """Pick up to `n` templates, weighted by `_TEMPLATE_WEIGHT`, never two on the
    same metric (so a day can't stack three walking quests). Deterministic for a
    given `rng`."""
    pool = list(templates)
    picks = []
    while pool and len(picks) < n:
        weights = [_TEMPLATE_WEIGHT.get(t[0], 5) for t in pool]
        choice = rng.choices(pool, weights=weights, k=1)[0]
        picks.append(choice)
        metric = choice[2]
        pool = [t for t in pool if t[2] != metric]
    return picks


def migrate(raw: dict) -> dict:
    """Upgrade a persisted QuestLog dict to CURRENT_SCHEMA in place. v1 files
    (no version, daily-only) gain the empty weekly + bonus blocks."""
    v = int(raw.get("schema_version", 1))
    if v < 2:
        raw.setdefault("week", "")
        raw.setdefault("weeklies", [])
        raw.setdefault("bonus_day", "")
    raw["schema_version"] = CURRENT_SCHEMA
    return raw


class QuestLog:
    def __init__(self, path: str):
        self.path = os.path.expanduser(path)
        self.schema_version: int = CURRENT_SCHEMA
        self.day: str = ""
        self.quests: list[Quest] = []          # dailies
        self.week: str = ""
        self.weeklies: list[Quest] = []
        self.bonus_day: str = ""               # day the all-clear bonus was paid
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path) as f:
                raw = json.load(f)
            raw = migrate(raw if isinstance(raw, dict) else {})
            self.schema_version = int(raw.get("schema_version", CURRENT_SCHEMA))
            self.day = raw.get("day", "")
            self.quests = [Quest.from_dict(d) for d in raw.get("quests", [])]
            self.week = raw.get("week", "")
            self.weeklies = [Quest.from_dict(d) for d in raw.get("weeklies", [])]
            self.bonus_day = raw.get("bonus_day", "")
        except Exception:
            self.day, self.quests = "", []
            self.week, self.weeklies, self.bonus_day = "", [], ""

    def save(self) -> None:
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({
                "schema_version": CURRENT_SCHEMA,
                "day": self.day,
                "quests": [q.to_dict() for q in self.quests],
                "week": self.week,
                "weeklies": [q.to_dict() for q in self.weeklies],
                "bonus_day": self.bonus_day,
            }, f, indent=2)
        os.replace(tmp, self.path)

    def roll(self, day: str, n: int = 3, rng=random) -> list:
        """Ensure today's active dailies exist. If the stored day differs from
        `day`, pick `n` weighted distinct-metric templates as the new active set
        (progress reset). Deterministic given `rng`."""
        if self.day != day:
            n = max(0, min(n, len(_TEMPLATES)))
            self.quests = [_template_quest(t)
                           for t in _weighted_distinct(_TEMPLATES, n, rng)]
            self.day = day
        return self.quests

    def roll_weekly(self, week: str, n: int = 2, rng=random) -> list:
        """Ensure this week's weekly quests exist (rerolled when `week` changes)."""
        if self.week != week:
            n = max(0, min(n, len(_WEEKLY_TEMPLATES)))
            self.weeklies = [_template_quest(t)
                             for t in _weighted_distinct(_WEEKLY_TEMPLATES, n, rng)]
            self.week = week
        return self.weeklies

    def record(self, metric: str, amount: float, rng=random) -> list:
        """Bump matching active, not-yet-done dailies AND weeklies. Returns every
        quest newly completed by this call -- each is a distinct quest object, so
        a caller granting one reward per returned quest never double-pays (a
        single event can legitimately finish a daily and a weekly = two rewards)."""
        newly: list = []
        for q in list(self.quests) + list(self.weeklies):
            if q.done or q.metric != metric:
                continue
            q.progress += amount
            if q.progress >= q.target:
                q.done = True
                newly.append(q)
        return newly

    def all_dailies_done(self) -> bool:
        return bool(self.quests) and all(q.done for q in self.quests)

    def claim_daily_bonus(self, day: str) -> int:
        """Return DAILY_CLEAR_BONUS the first time every daily is cleared on
        `day`, else 0. Stamps bonus_day so it pays at most once per day."""
        if self.all_dailies_done() and self.bonus_day != day:
            self.bonus_day = day
            return DAILY_CLEAR_BONUS
        return 0

    def active(self) -> list:
        return list(self.quests)

    def active_weeklies(self) -> list:
        return list(self.weeklies)


def _credit_scrap(cfg, wallet, amount: int) -> None:
    """Credit scrap to the supplied wallet (caller saves it), or to a freshly
    loaded+saved wallet when none is passed (CLI one-shot grant). Threading a
    shared wallet avoids the multi-instance clobber the design flagged."""
    if amount <= 0:
        return
    if wallet is not None:
        wallet.earn(amount)
        return
    from .shop import Wallet
    w = Wallet(getattr(cfg, "wallet_path", "~/.flippergotchi/wallet.json"))
    w.earn(amount)
    w.save()


def grant_quest_reward(quest, state, inv, cfg, wallet=None) -> str:
    """Apply a completed quest's reward to the player. Kept here (not in the
    pure data classes) so callers don't duplicate the reward logic. Imports are
    local to avoid any package import cycle. ``wallet`` (optional) lets a caller
    that already holds a Wallet take the scrap credit and save once."""
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
    if r.get("scrap"):
        _credit_scrap(cfg, wallet, int(r["scrap"]))
        msgs.append(f"+{r['scrap']} scrap")
    if r.get("food"):
        for _ in range(int(r["food"])):
            mechanics.snack(state, cfg)
        msgs.append(f"+{r['food']} food")
    if r.get("gear") and inv is not None:
        it = inv.add(equipment.roll_item(boost=state.level // 2))
        msgs.append(f"gear: {it.name}")
    return ", ".join(msgs) or "no reward"
