"""Equipment: find gear pieces, slot them onto your character, win duels with them.

Slots (one item each): helmet, eyepiece, amulet, weapon, fin. Each item rolls a
PvP stat (ATK / DEF / LUCK). Equipped gear's combined power boosts your strength
in **PvP duels ONLY** — it does NOT help against WiFi monsters, since cracking is
a deterministic wordlist attack, not a stat check. Gear is looted from captures
and walks; the loser of a duel forfeits a piece to the winner.
"""
from __future__ import annotations

import json
import os
import random
from dataclasses import asdict, dataclass

# body-part / hand slots you can equip a piece into
SLOTS = ["helmet", "eyepiece", "amulet", "weapon", "fin"]
RARITIES = ["common", "uncommon", "rare", "epic", "legendary"]
_RARITY_POWER = {"common": 3, "uncommon": 6, "rare": 11, "epic": 18, "legendary": 28}
_RARITY_WEIGHT = [50, 28, 14, 6, 2]
_ADJ = {"common": "Scuffed", "uncommon": "Sturdy", "rare": "Tuned",
        "epic": "Prismatic", "legendary": "Mythic"}
# a few flavour names per slot (weapons get the most variety)
_NOUN = {
    "helmet": ["Helm", "War Crown", "Battle Hood", "Skull Cap", "Visor-Helm"],
    "eyepiece": ["Monocle", "Targeting Visor", "HUD Lens", "Optic Spike", "Scope"],
    "amulet": ["Amulet", "Tooth Pendant", "Power Core", "Sigil", "Reef Charm"],
    "weapon": ["Shiv", "Net Cannon", "Shock Prod", "Plasma Cutlass", "Rail Spear",
               "Buzz-Saw", "Harpoon"],
    "fin": ["Crest", "Razor Fin", "Aero Blade", "War Spine", "Spoiler"],
}
# each slot's primary PvP stat (ATK = offense, DEF = defense, LUCK = upset odds)
_SLOT_STAT = {"weapon": "atk", "fin": "atk", "helmet": "def",
              "amulet": "luck", "eyepiece": "luck"}


@dataclass
class Item:
    id: str
    name: str
    slot: str
    rarity: str
    power: int
    bonus_stat: str = ""     # atk | def | luck (PvP)
    bonus_val: float = 0.0
    set: str = ""            # gear-set tag (see gearsets.py); "" = no set

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Item":
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in d.items() if k in known})


def roll_item(rng=random, boost: int = 0) -> Item:
    """Generate a random loot item; `boost` (e.g. peer level) sweetens power.

    Rarer drops (rare+) are more likely to belong to a named gear-set (see
    gearsets.py); commons usually stay set-less. The set tag is purely a PvP
    flavour layer — it never touches WiFi cracking.
    """
    slot = rng.choice(SLOTS)
    rarity = rng.choices(RARITIES, weights=_RARITY_WEIGHT)[0]
    power = _RARITY_POWER[rarity] + max(0, boost)
    stat = _SLOT_STAT[slot]
    val = power  # the PvP stat scales with the item's power
    iid = f"{slot}-{rarity[:3]}-{rng.randrange(1 << 24):06x}"
    set_tag = _roll_set_tag(rarity, rng)
    return Item(id=iid, name=f"{_ADJ[rarity]} {rng.choice(_NOUN[slot])}", slot=slot,
                rarity=rarity, power=power, bonus_stat=stat, bonus_val=val,
                set=set_tag)


# chance a drop carries a set tag, by rarity (commons mostly plain)
_SET_CHANCE = {"common": 0.05, "uncommon": 0.20, "rare": 0.45,
               "epic": 0.70, "legendary": 1.0}


def _roll_set_tag(rarity: str, rng=random) -> str:
    """Maybe assign a gear-set tag. Local import keeps equipment.py importable
    even if gearsets.py is absent (back-compat / partial installs)."""
    if rng.random() >= _SET_CHANCE.get(rarity, 0.0):
        return ""
    try:
        from . import gearsets
        names = gearsets.set_names()
    except Exception:
        return ""
    return rng.choice(names) if names else ""


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
        except Exception:
            return
        if not isinstance(raw, dict):
            return
        # tolerant load: skip only the malformed rows, keep the rest of the bag.
        rows = raw.get("items", [])
        for d in rows if isinstance(rows, list) else []:
            try:
                it = Item.from_dict(d)
                self.items[it.id] = it
            except Exception:
                continue
        eq = raw.get("equipped", {})
        if isinstance(eq, dict):
            self.equipped = {s: i for s, i in eq.items() if i in self.items}

    def save(self) -> None:
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = f"{self.path}.tmp.{os.getpid()}"
        with open(tmp, "w") as f:
            json.dump({"items": [it.to_dict() for it in self.items.values()],
                       "equipped": self.equipped}, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
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

    def set_bonus(self) -> dict:
        """PvP bonus from any completed/partial gear sets among equipped items.
        Returns a dict like {"power": int, "atk": .., "def": .., "luck": ..}.
        Empty/zero when no set thresholds are met. PvP ONLY."""
        try:
            from . import gearsets
        except Exception:
            return {}
        return gearsets.set_bonus(self.equipped_items())

    def pvp_power(self) -> int:
        """Total PvP power: raw gear_power() plus any gear-set power bonus. This
        is the duel-facing number; gear_power() keeps its original meaning so
        existing callers/tests are untouched. NEVER used for WiFi cracking."""
        return self.gear_power() + int(self.set_bonus().get("power", 0))

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
