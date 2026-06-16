"""In-game shop + currency ("scrap").

Scrap is salvaged data, measured in bytes, that the pet earns from its hustle:
cracking networks, walking, and winning duels. It's spent in the :class:`Shop`
on consumables and gear utilities.

Persistence: a tiny :class:`Wallet` JSON store (atomic tmp + os.replace, like
Ledger). We deliberately keep the balance in its own file rather than touching
pet/state.py — PetState is owned elsewhere — but :class:`Wallet` will also read
a balance off a state object via getattr if a caller prefers that, falling back
gracefully.

`Shop.buy()` NEVER raises: it returns ``(ok, message)`` and applies the item's
effect only on success. Earn-rule helpers are exposed for the agent to wire up;
they are pure functions and are intentionally NOT called from agent.py here.

Nothing in this module touches WiFi cracking outcomes — scrap is a reward for
cracks, not an input to them.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

# ---- earn rules (pure helpers; agent.py wires these up itself) --------------
SCRAP_PER_CRACK = 120
SCRAP_PER_DUEL_WIN = 60
SCRAP_PER_KM = 40            # walking salvages this much per kilometre
SCRAP_PER_CATCH = 15


def scrap_for_crack() -> int:
    return SCRAP_PER_CRACK


def scrap_for_duel_win() -> int:
    return SCRAP_PER_DUEL_WIN


def scrap_for_walk(meters: float) -> int:
    """Scrap earned for walking `meters` (rounded down)."""
    return int(max(0.0, meters) / 1000.0 * SCRAP_PER_KM)


def scrap_for_catch() -> int:
    return SCRAP_PER_CATCH


# ---- wallet -----------------------------------------------------------------
class Wallet:
    def __init__(self, path: str):
        self.path = os.path.expanduser(path)
        self.scrap: int = 0
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path) as f:
                raw = json.load(f)
            self.scrap = int(raw.get("scrap", 0)) if isinstance(raw, dict) else int(raw)
        except Exception:
            self.scrap = 0

    def save(self) -> None:
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"scrap": int(self.scrap)}, f, indent=2)
        os.replace(tmp, self.path)

    def earn(self, amount: int) -> int:
        """Add scrap (negatives ignored). Returns new balance."""
        if amount and amount > 0:
            self.scrap += int(amount)
        return self.scrap

    def can_afford(self, cost: int) -> bool:
        return self.scrap >= int(cost)

    def spend(self, cost: int) -> bool:
        """Deduct `cost` if affordable. Returns True on success."""
        cost = int(cost)
        if cost < 0 or self.scrap < cost:
            return False
        self.scrap -= cost
        return True


# ---- shop catalogue ---------------------------------------------------------
@dataclass
class ShopItem:
    id: str
    name: str
    cost: int
    description: str
    effect: str            # dispatch key handled in Shop._apply
    magnitude: float = 0.0


CATALOG: list[ShopItem] = [
    ShopItem("ration", "Food Ration", 60,
             "Restore some hunger (feed the pet)", "feed", 25.0),
    ShopItem("feast", "Salvage Feast", 140,
             "A big meal — restore lots of hunger", "feed", 60.0),
    ShopItem("energy_snack", "Energy Snack", 90,
             "Restore energy", "energy", 35.0),
    ShopItem("repair_kit", "Repair Kit", 110,
             "Restore health", "health", 40.0),
    ShopItem("lure", "Monster Lure", 150,
             "Consumable: boosts encounter rate (sets a lure flag)", "lure", 1.0),
    ShopItem("reroll_token", "Gear Reroll Token", 220,
             "Reroll an UNEQUIPPED item's rarity/stats", "reroll", 1.0),
]

_BY_ID = {it.id: it for it in CATALOG}


class Shop:
    def __init__(self, cfg=None):
        self.cfg = cfg

    def list_items(self) -> list[ShopItem]:
        return list(CATALOG)

    def get(self, item_id: str) -> ShopItem | None:
        return _BY_ID.get(item_id)

    def buy(self, wallet: Wallet, item_id: str, inv=None, state=None,
            target_item_id: str | None = None, rng=None) -> tuple[bool, str]:
        """Purchase `item_id`, charging `wallet` and applying the effect.

        Returns (ok, message). Never raises. On insufficient funds or a
        non-applicable effect (e.g. reroll with no eligible item) nothing is
        charged. `target_item_id` selects which inventory item a reroll touches.
        """
        item = _BY_ID.get(item_id)
        if item is None:
            return False, f"No such item: {item_id}"
        if not wallet.can_afford(item.cost):
            return (False,
                    f"Not enough scrap for {item.name} "
                    f"(need {item.cost}, have {wallet.scrap})")
        ok, msg = self._apply(item, inv=inv, state=state,
                              target_item_id=target_item_id, rng=rng)
        if not ok:
            return False, msg          # effect couldn't apply -> no charge
        wallet.spend(item.cost)
        return True, f"{msg} (-{item.cost} scrap, {wallet.scrap} left)"

    # -- effect dispatch ------------------------------------------------------
    def _apply(self, item: ShopItem, inv=None, state=None,
               target_item_id: str | None = None, rng=None) -> tuple[bool, str]:
        eff = item.effect
        if eff in ("feed", "energy", "health"):
            return self._apply_stat(eff, item.magnitude, state)
        if eff == "lure":
            return self._apply_lure(state)
        if eff == "reroll":
            return self._apply_reroll(inv, target_item_id, rng)
        return False, f"Unknown effect for {item.name}"

    @staticmethod
    def _apply_stat(eff: str, mag: float, state) -> tuple[bool, str]:
        if state is None:
            return False, "Nobody to use that on"
        if eff == "feed":
            # hunger: 0 = full, 100 = starving -> feeding lowers it
            cur = getattr(state, "hunger", 0.0)
            setattr(state, "hunger", max(0.0, cur - mag))
            return True, f"Fed the pet (-{mag:g} hunger)"
        if eff == "energy":
            cur = getattr(state, "energy", 0.0)
            setattr(state, "energy", min(100.0, cur + mag))
            return True, f"Energy restored (+{mag:g})"
        if eff == "health":
            cur = getattr(state, "health", 0.0)
            setattr(state, "health", min(100.0, cur + mag))
            return True, f"Health restored (+{mag:g})"
        return False, "No effect"

    @staticmethod
    def _apply_lure(state) -> tuple[bool, str]:
        if state is None:
            return False, "No pet to carry the lure"
        # consumable flag the encounter system can read defensively
        count = int(getattr(state, "lures", 0) or 0) + 1
        setattr(state, "lures", count)
        return True, f"Lure ready (x{count}) — encounter rate boosted"

    @staticmethod
    def _apply_reroll(inv, target_item_id, rng) -> tuple[bool, str]:
        if inv is None:
            return False, "No inventory to reroll from"
        from . import equipment
        import random as _random
        rng = rng or _random
        # eligible: items that exist and are NOT currently equipped
        eligible = [it for it in inv.items.values() if not inv.is_equipped(it.id)]
        if not eligible:
            return False, "No unequipped item to reroll"
        if target_item_id is not None:
            old = inv.items.get(target_item_id)
            if old is None or inv.is_equipped(target_item_id):
                return False, "That item can't be rerolled"
        else:
            old = rng.choice(eligible)
        fresh = equipment.roll_item(rng=rng)
        # keep the slot stable so the reroll is a same-slot upgrade attempt
        fresh.slot = old.slot
        fresh.bonus_stat = equipment._SLOT_STAT[old.slot]
        fresh.id = old.id          # reuse id so equip refs stay valid
        inv.items[old.id] = fresh
        return True, (f"Rerolled {old.name} -> {fresh.name} "
                      f"({fresh.rarity}, power {fresh.power})")
