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

    stage: str = "egg"        # evolution stage, driven by level
    asleep: bool = False

    def age_seconds(self) -> float:
        return max(0.0, time.time() - self.born_at)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PetState":
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in d.items() if k in known})
