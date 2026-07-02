from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field


@dataclass
class PetState:
    """Everything that makes the pet *this* pet. Serialised to disk."""

    name: str = "Flippy"
    born_at: float = field(default_factory=time.time)

    level: int = 1
    xp: float = 0.0

    # 0 = full / 100 = starving. Handshakes are food, so capturing lowers this.
    hunger: float = 20.0
    happiness: float = 70.0   # 0..100
    energy: float = 100.0     # 0..100
    health: float = 100.0     # 0..100

    distance_m: float = 0.0   # total metres walked (GPS)
    handshakes: int = 0
    pmkids: int = 0
    networks_seen: int = 0
    duel_wins: int = 0        # PvP duels won (achievements/progression)

    stage: str = "egg"        # evolution stage, driven by level
    # Your duel element (Spark/Tide/Gale/Aether). First-class: settable at
    # init/from config (use set_element for validated input), persisted via
    # to_dict/from_dict, and READ by the duel resolver -- it is the player's
    # side of the type chart, not a frozen default.
    element: str = "Aether"
    asleep: bool = False

    # --- v2: active-care + cosmetics + mode (all default-safe for old saves) ---
    # satiety: a short-lived "well-fed" buff (0..100) that decays over time and
    # gives a small PvP/forage edge ONLY -- it never touches WiFi/BLE cracking.
    satiety: float = 0.0
    titles: list = field(default_factory=list)   # earned cosmetic titles
    active_title: str = ""
    # cosmetic skins bought from the shop (e.g. "skin_goldfin"); persisted so a
    # purchase survives a reload. Purely decorative -- never touches combat.
    skins: list = field(default_factory=list)
    # hardcore: opt-in at creation, LOCKED for this pet's life. Starvation kills
    # (reset to egg) instead of flooring at 1 HP. Default False = the safe model.
    hardcore: bool = False

    # --- v2.1: endgame/retention (all default-safe for old saves) ---
    # paragon: post-L40 prestige marker. Persisted here; INCREMENTED by the
    # evolution/mechanics layer (which reads it via getattr), never by this
    # module -- 0 means the pet has not crossed into paragon play yet.
    paragon: int = 0

    # On-disk schema version. Kept LAST so old saves lacking it still load and
    # positional/keyword construction in tests stays valid. Bumped by the
    # migrator in persistence.py when the shape of this dataclass changes.
    schema_version: int = 2

    def age_seconds(self) -> float:
        return max(0.0, time.time() - self.born_at)

    def set_element(self, element: str) -> bool:
        """Set the duel element from user/config input, tolerantly.

        Accepts canonical names plus common aliases (case-insensitive
        "spark"/"tide"/"gale"/"aether", band spellings like "2.4GHz", "BLE").
        Returns True and updates ``self.element`` on success; leaves the
        element untouched and returns False for unknown values.
        """
        from ..game.elements import normalize
        el = normalize(element)
        if el is None:
            return False
        self.element = el
        return True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PetState":
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in d.items() if k in known})
