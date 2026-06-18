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
# v3 adds lifetime/streak tracking (lifetime_done, streak, last_clear_day).
CURRENT_SCHEMA = 3
# one-time scrap for clearing every daily in a day (the "finish the set" nudge).
DAILY_CLEAR_BONUS = 45


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
# so a full clear of `n` dailies + the all-clear bonus averages ~150/day (see the
# Monte-Carlo regression in test_quest_economy.py that pins the mean to a band).
_TEMPLATES = [
    ("walk_2k", "Walk 2 km", "distance_m", 2000, {"xp": 50, "scrap": 30}),
    ("walk_5k", "Walk 5 km", "distance_m", 5000, {"xp": 140, "scrap": 40}),
    ("catch_5", "Catch 5 monsters", "catches", 5, {"handshakes": 3, "scrap": 35}),
    ("crack_1", "Crack a network", "cracks", 1, {"xp": 80, "scrap": 45}),
    ("duel_1", "Win a duel", "duel_wins", 1, {"gear": True, "scrap": 35}),
    ("forage_3", "Forage 3 snacks", "snacks", 3, {"xp": 30, "scrap": 25}),
    ("tame_2", "Tame 2 Bluetooth devices", "tames", 2, {"xp": 40, "scrap": 35}),
    ("legend_1", "Crack a WEP/WPA1 legendary", "legendary_kills", 1, {"scrap": 45}),
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


@dataclass
class ChainStep:
    description: str
    metric: str
    target: float
    reward: dict


# Quest CHAINS: multi-step storylines from named givers. Definitions live here in
# code; only per-chain progress ({step, progress, done}) is persisted. The active
# step of each unfinished chain shows alongside the dailies. Chains are lifetime
# (never reroll) -- a long-tail spine the daily/weekly loops lack.
_CHAINS = [
    ("first_steps", "Old Salt", "First Steps", [
        ChainStep("Walk 1 km", "distance_m", 1000, {"scrap": 30}),
        ChainStep("Catch 3 monsters", "catches", 3, {"scrap": 40}),
        ChainStep("Crack your first network", "cracks", 1, {"scrap": 60, "gear": True}),
    ]),
    ("the_hunt", "Reefwarden", "The Hunt", [
        ChainStep("Catch 20 monsters", "catches", 20, {"scrap": 60}),
        ChainStep("Crack 5 networks", "cracks", 5, {"scrap": 90}),
        ChainStep("Crack a WEP/WPA1 legendary", "legendary_kills", 1,
                  {"scrap": 160, "gear": True}),
    ]),
    ("ghost_protocol", "Nullbyte", "Ghost Protocol", [
        ChainStep("Tame 5 Bluetooth devices", "tames", 5, {"scrap": 50}),
        ChainStep("Win 3 duels", "duel_wins", 3, {"scrap": 90}),
        ChainStep("Walk 10 km", "distance_m", 10000, {"scrap": 140, "gear": True}),
    ]),
]
_CHAIN_BY_ID = {cid: (giver, title, steps) for cid, giver, title, steps in _CHAINS}


def _load_quest_rows(rows) -> list:
    """Tolerant row parse: skip only the malformed quest entries (a single bad
    row must not blank the whole daily/weekly set)."""
    out: list = []
    for d in rows if isinstance(rows, list) else []:
        try:
            out.append(Quest.from_dict(d))
        except Exception:
            continue
    return out


def _day_gap(a: str, b: str):
    """Whole-day gap between two YYYY-MM-DD strings (b - a), or None if either is
    unparseable. Pure date arithmetic on the passed-in strings -- no clock read,
    so streak adjacency stays deterministic/testable."""
    from datetime import date
    try:
        ya, ma, da = (int(x) for x in a.split("-"))
        yb, mb, db = (int(x) for x in b.split("-"))
        return (date(yb, mb, db) - date(ya, ma, da)).days
    except Exception:
        return None


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
    """Upgrade a persisted QuestLog dict to CURRENT_SCHEMA in place. v1 (daily
    only) gains the weekly+bonus blocks; v2 gains lifetime/streak tracking."""
    v = int(raw.get("schema_version", 1))
    if v < 2:
        raw.setdefault("week", "")
        raw.setdefault("weeklies", [])
        raw.setdefault("bonus_day", "")
    if v < 3:
        raw.setdefault("lifetime_done", 0)
        raw.setdefault("streak", 0)
        raw.setdefault("last_clear_day", "")
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
        self.lifetime_done: int = 0            # total quests ever completed
        self.streak: int = 0                   # consecutive all-dailies-clear days
        self.last_clear_day: str = ""
        self.chains: dict = {}                 # chain_id -> {step, progress, done}
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
            self.quests = _load_quest_rows(raw.get("quests"))
            self.week = raw.get("week", "")
            self.weeklies = _load_quest_rows(raw.get("weeklies"))
            self.bonus_day = raw.get("bonus_day", "")
            self.lifetime_done = int(raw.get("lifetime_done", 0))
            self.streak = int(raw.get("streak", 0))
            self.last_clear_day = raw.get("last_clear_day", "")
            self.chains = raw.get("chains", {}) if isinstance(raw.get("chains"), dict) else {}
        except Exception:
            self.day, self.quests = "", []
            self.week, self.weeklies, self.bonus_day = "", [], ""
            self.lifetime_done, self.streak, self.last_clear_day = 0, 0, ""
            self.chains = {}

    def save(self) -> None:
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = f"{self.path}.tmp.{os.getpid()}"
        with open(tmp, "w") as f:
            json.dump({
                "schema_version": CURRENT_SCHEMA,
                "day": self.day,
                "quests": [q.to_dict() for q in self.quests],
                "week": self.week,
                "weeklies": [q.to_dict() for q in self.weeklies],
                "bonus_day": self.bonus_day,
                "lifetime_done": self.lifetime_done,
                "streak": self.streak,
                "last_clear_day": self.last_clear_day,
                "chains": self.chains,
            }, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    def roll(self, day: str, n: int = 3, rng=random) -> list:
        """Ensure today's active dailies exist. If the stored day differs from
        `day`, pick `n` weighted distinct-metric templates as the new active set
        (progress reset). Deterministic given `rng`."""
        if self.day != day:
            # a new day breaks the consecutive-clear streak if EITHER the day we
            # just left wasn't fully cleared, OR a calendar day was skipped
            # entirely (the new day isn't the one right after our last all-clear).
            if self.day and not self.all_dailies_done():
                self.streak = 0
            elif self.last_clear_day:
                gap = _day_gap(self.last_clear_day, day)
                if gap is not None and gap > 1:
                    self.streak = 0
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
        newly += self._advance_chains(metric, amount)
        self.lifetime_done += len(newly)      # feeds the quests_done capstone
        return newly

    def _advance_chains(self, metric: str, amount: float) -> list:
        """Advance any chain whose CURRENT step tracks `metric`. Returns the
        completed steps as Quest objects (so the caller grants them uniformly)."""
        done_steps: list = []
        for cid, (giver, title, steps) in _CHAIN_BY_ID.items():
            cs = self.chains.get(cid) or {"step": 0, "progress": 0.0, "done": False}
            if cs.get("done") or cs.get("step", 0) >= len(steps):
                continue
            step = steps[cs["step"]]
            if step.metric != metric:
                self.chains[cid] = cs
                continue
            cs["progress"] = cs.get("progress", 0.0) + amount
            if cs["progress"] >= step.target:
                done_steps.append(Quest(
                    id=f"{cid}:{cs['step']}",
                    description=f"[{giver}] {step.description}",
                    metric=step.metric, target=step.target,
                    progress=step.target, done=True, reward=dict(step.reward)))
                cs["step"] += 1
                cs["progress"] = 0.0
                if cs["step"] >= len(steps):
                    cs["done"] = True
            self.chains[cid] = cs
        return done_steps

    def active_chains(self) -> list:
        """For display: (giver, title, step_desc, progress, target, idx, total) for
        each unfinished chain's current step."""
        out = []
        for cid, (giver, title, steps) in _CHAIN_BY_ID.items():
            cs = self.chains.get(cid) or {"step": 0, "progress": 0.0, "done": False}
            i = cs.get("step", 0)
            if cs.get("done") or i >= len(steps):
                continue
            st = steps[i]
            out.append((giver, title, st.description, cs.get("progress", 0.0),
                        st.target, i + 1, len(steps)))
        return out

    def all_dailies_done(self) -> bool:
        return bool(self.quests) and all(q.done for q in self.quests)

    def claim_daily_bonus(self, day: str) -> int:
        """Return DAILY_CLEAR_BONUS the first time every daily is cleared on
        `day`, else 0. Stamps bonus_day so it pays at most once per day."""
        if self.all_dailies_done() and self.bonus_day != day:
            self.bonus_day = day
            self.streak += 1                  # another consecutive clear
            self.last_clear_day = day
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
