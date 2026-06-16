"""Equipment system: gear you loot, equip for stat bonuses, and can lose in duels.

Slots (one item each): antenna, battery, cpu, charm, hull.
Only *equipped* gear contributes to your power. Gear is looted from captures and
won in duels; the loser of a duel forfeits a piece of gear to the winner.
"""
from __future__ import annotations

import json
import os
import random
from dataclasses import asdict, dataclass

SLOTS = ["antenna", "battery", "cpu", "charm", "hull"]
RARITIES = ["common", "uncommon", "rare", "epic", "legendary"]
_RARITY_POWER = {"common": 3, "uncommon": 6, "rare": 11, "epic": 18, "legendary": 28}
_RARITY_WEIGHT = [50, 28, 14, 6, 2]
_ADJ = {"common": "Scuffed", "uncommon": "Sturdy", "rare": "Tuned",
        "epic": "Prismatic", "legendary": "Mythic"}
_NOUN = {"antenna": "Antenna", "battery": "Cell", "cpu": "Coprocessor",
         "charm": "Charm", "hull": "Hull"}
# each slot mainly buffs one stat (hooks for capture/crack/xp/duel/luck)
_SLOT_BONUS = {
    "antenna": ("capture", 0.04),
    "battery": ("energy", 0.10),
    "cpu": ("crack", 0.05),
    "charm": ("luck", 0.03),
    "hull": ("duel", 1.0),
}


@dataclass
class Item:
    id: str
    name: str
    slot: str
    rarity: str
    power: int
    bonus_stat: str = ""
    bonus_val: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Item":
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in d.items() if k in known})


def roll_item(rng=random, boost: int = 0) -> Item:
    """Generate a random loot item; `boost` (e.g. peer level) sweetens power."""
    slot = rng.choice(SLOTS)
    rarity = rng.choices(RARITIES, weights=_RARITY_WEIGHT)[0]
    power = _RARITY_POWER[rarity] + max(0, boost)
    stat, base = _SLOT_BONUS[slot]
    val = round(base * (1 + RARITIES.index(rarity)), 3)
    iid = f"{slot}-{rarity[:3]}-{rng.randrange(1 << 24):06x}"
    return Item(id=iid, name=f"{_ADJ[rarity]} {_NOUN[slot]}", slot=slot,
                rarity=rarity, power=power, bonus_stat=stat, bonus_val=val)


class Inventory:
    def __init__(self, path: str):
        self.path = os.path.expanduser(path)
        self.items: dict[str, Item] = {}
        self.equipped: dict[str, str] = {}   # slot -> item id
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path) as f:
                raw = json.load(f)
            self.items = {d["id"]: Item.from_dict(d) for d in raw.get("items", [])}
            self.equipped = {s: i for s, i in raw.get("equipped", {}).items()
                             if i in self.items}
        except Exception:
            self.items, self.equipped = {}, {}

    def save(self) -> None:
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"items": [it.to_dict() for it in self.items.values()],
                       "equipped": self.equipped}, f, indent=2)
        os.replace(tmp, self.path)

    def add(self, item: Item) -> Item:
        self.items[item.id] = item
        return item

    def remove(self, item_id: str) -> Item | None:
        self.equipped = {s: i for s, i in self.equipped.items() if i != item_id}
        return self.items.pop(item_id, None)

    def equip(self, item_id: str) -> Item | None:
        it = self.items.get(item_id)
        if it:
            self.equipped[it.slot] = item_id
        return it

    def unequip_slot(self, slot: str) -> str | None:
        return self.equipped.pop(slot, None)

    def is_equipped(self, item_id: str) -> bool:
        return item_id in self.equipped.values()

    def equipped_items(self) -> list:
        return [self.items[i] for i in self.equipped.values() if i in self.items]

    def gear_power(self) -> int:
        return sum(it.power for it in self.equipped_items())

    def all(self) -> list:
        return sorted(self.items.values(), key=lambda x: (-x.power, x.slot))

    def pick_forfeit(self, rng=random) -> Item | None:
        """The 'bit of gear' a loser hands over: an unequipped item if possible,
        otherwise the weakest item; least valuable first."""
        if not self.items:
            return None
        unequipped = [it for it in self.items.values() if not self.is_equipped(it.id)]
        pool = unequipped or list(self.items.values())
        return min(pool, key=lambda x: x.power)
