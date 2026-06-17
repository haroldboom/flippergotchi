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
    reward: dict = field(default_factory=dict)   # {scrap, food, gear:bool}
    # --- presentation metadata (all defaulted so legacy badges are unchanged) ---
    category: str = "general"   # catch|crack|duel|walk|bluetooth|meta|general
    series: str = ""            # groups a tiered ladder (e.g. "beastmaster")
    tier: str = ""              # bronze|silver|gold|"" (cosmetic rank)
    hidden: bool = False        # masked as "???" in the list until unlocked

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


# The badge catalogue, grouped into tiered series. Rewards stay small so
# achievements supplement, not replace, the core economy; only a few gold
# capstones mint gear (capped to keep PvP/inventory from inflating).
CATALOG: list[Badge] = [
    # -- catches: the Beastmaster ladder --
    Badge("first_catch", "First Blood", "Catch your first monster",
          "catches", 1, {"scrap": 50}, "catch", "beastmaster", "bronze"),
    Badge("catch_10", "Beastmaster I", "Catch 10 monsters",
          "catches", 10, {"scrap": 100}, "catch", "beastmaster", "bronze"),
    Badge("catch_50", "Beastmaster II", "Catch 50 monsters",
          "catches", 50, {"scrap": 300}, "catch", "beastmaster", "silver"),
    Badge("catch_100", "Beastmaster III", "Catch 100 monsters",
          "catches", 100, {"scrap": 600, "food": 5, "gear": True,
                           "title": "the Beastmaster"},
          "catch", "beastmaster", "gold"),
    # -- cracks: the Safecracker ladder --
    Badge("crack_1", "Lockpicker", "Crack your first network",
          "cracks", 1, {"scrap": 80}, "crack", "safecracker", "bronze"),
    Badge("crack_10", "Safecracker", "Crack 10 networks",
          "cracks", 10, {"scrap": 250}, "crack", "safecracker", "silver"),
    Badge("crack_50", "Cipherbane", "Crack 50 networks",
          "cracks", 50, {"scrap": 600, "gear": True},
          "crack", "safecracker", "gold"),
    Badge("legend_3", "Mythbreaker", "Crack 3 WEP/WPA1 legendaries",
          "legendary_kills", 3, {"scrap": 350}, "crack", "legendary", "gold"),
    # -- duels: the Gladiator ladder --
    Badge("duel_win_5", "Brawler", "Win 5 duels",
          "duel_wins", 5, {"scrap": 120}, "duel", "gladiator", "bronze"),
    Badge("duel_win_25", "Gladiator", "Win 25 duels",
          "duel_wins", 25, {"scrap": 400, "food": 3, "title": "the Gladiator"},
          "duel", "gladiator", "gold"),
    # -- walking: the Trailblazer ladder --
    Badge("walk_10k_m", "Trailblazer", "Walk 10 km total",
          "distance_m", 10000, {"scrap": 150}, "walk", "trailblazer", "bronze"),
    Badge("walk_50k_m", "Marathoner", "Walk 50 km total",
          "distance_m", 50000, {"scrap": 500, "food": 5}, "walk", "trailblazer", "gold"),
    # -- bluetooth: the Whisperer ladder (phase-3 `tames` metric) --
    Badge("tame_10", "Whisperer", "Tame 10 Bluetooth devices",
          "tames", 10, {"scrap": 150}, "bluetooth", "whisperer", "silver"),
    Badge("tame_50", "Ghost in the Machine", "Tame 50 Bluetooth devices",
          "tames", 50, {"scrap": 500, "gear": True}, "bluetooth", "whisperer", "gold"),
    # -- meta milestones --
    Badge("level_10", "Seasoned", "Reach level 10",
          "level", 10, {"scrap": 200}, "meta", "", "silver"),
    Badge("evolve_to_legend", "Ascended", "Evolve into a legendary form",
          "stage_legend", 1, {"scrap": 500, "food": 5, "title": "the Ascended"},
          "meta", "", "gold"),
    Badge("full_loadout", "Geared Up", "Equip all 5 gear slots at once",
          "equipped_slots", FULL_LOADOUT_SLOTS, {"scrap": 180}, "meta", "", "silver"),
    # -- hidden / secret (masked until unlocked; shiny mechanic is future) --
    Badge("shiny_find", "Sparkle", "Find a shiny monster",
          "shinies", 1, {"scrap": 300, "food": 3}, "meta", "", "gold", hidden=True),
]

_BY_ID = {b.id: b for b in CATALOG}


def get(badge_id: str) -> Badge | None:
    return _BY_ID.get(badge_id)


def build_stats(state, dex=None, inv=None, ledger=None) -> dict:
    """The single progress snapshot the catalogue checks against, sourced from the
    live stores so the agent loop and the CLI agree. In particular ``cracks`` comes
    from the Ledger in BOTH (the agent path used to hardcode 0, so crack badges
    could never unlock during normal play)."""
    catches = sum(1 for x in dex.all() if getattr(x, "captured", False)) if dex else 0
    cracks = ledger.counts().get("win", 0) if ledger else 0
    return {
        "catches": catches,
        "cracks": cracks,
        "duel_wins": getattr(state, "duel_wins", 0),
        "distance_m": getattr(state, "distance_m", 0.0),
        "level": getattr(state, "level", 1),
        "stage": getattr(state, "stage", "egg"),
        "equipped_slots": len(getattr(inv, "equipped", {}) or {}) if inv else 0,
        "shinies": 0,
    }


def grant_reward(book, stats, state, cfg, wallet=None, inv=None) -> list:
    """THE single achievement-reward site: unlock any newly-met badges and apply
    their rewards (scrap -> ``wallet`` [caller saves]; food -> mechanics.snack;
    ``gear:True`` -> a rolled item into ``inv`` for gold capstones). Returns the
    newly-unlocked badges. Idempotent via ``book.check`` (already-unlocked badges
    are skipped) so it never double-pays. View-only paths must NOT call this."""
    from ..pet import mechanics
    newly = book.check(stats)
    own = None
    for b in newly:
        rw = b.reward or {}
        s = int(rw.get("scrap", 0))
        if s:
            if wallet is not None:
                wallet.earn(s)
            else:
                from .shop import Wallet
                own = own or Wallet(getattr(cfg, "wallet_path",
                                            "~/.flippergotchi/wallet.json"))
                own.earn(s)
        for _ in range(int(rw.get("food", 0))):
            mechanics.snack(state, cfg)
        if rw.get("gear") and inv is not None:
            from . import equipment
            inv.add(equipment.roll_item(boost=getattr(state, "level", 1) // 2))
        title = rw.get("title")
        if title and hasattr(state, "titles") and title not in state.titles:
            state.titles.append(title)
            if not getattr(state, "active_title", ""):
                state.active_title = title          # auto-equip the first earned
    if own is not None:
        own.save()
    return newly


def display_name(badge, unlocked: bool) -> str:
    """A hidden badge stays masked until it is earned."""
    if badge.hidden and not unlocked:
        return "??? (secret)"
    return badge.name


def progress(badge, stats) -> tuple:
    """(current, threshold) toward a (locked) badge, for a progress readout."""
    return _stat_value(stats, badge.metric), badge.threshold


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
