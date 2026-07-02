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
they are pure functions; agent.py + the CLI call them to credit scrap.

Nothing in this module touches WiFi cracking outcomes — scrap is a reward for
cracks, not an input to them.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

# ---- earn rules (pure helpers; agent.py wires these up itself) --------------
SCRAP_PER_CRACK = 120       # real WEP/WPA crack — the top reward
SCRAP_PER_DUEL_WIN = 60
SCRAP_PER_KM = 40            # walking salvages this much per kilometre
SCRAP_PER_CATCH = 8         # catching (encountering) a monster/AP
SCRAP_PER_OPEN = 18         # walking into an OPEN network: catch-tier, NOT a crack


def scrap_for_crack() -> int:
    return SCRAP_PER_CRACK


def scrap_for_open() -> int:
    """Scrap for stumbling onto an OPEN (unsecured) network. There's no crack to
    perform, so this pays a catch-tier reward — deliberately far below
    :func:`scrap_for_crack` (a real WEP/WPA break)."""
    return SCRAP_PER_OPEN


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
        tmp = f"{self.path}.tmp.{os.getpid()}"
        with open(tmp, "w") as f:
            json.dump({"scrap": int(self.scrap)}, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
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
    food_id: str = ""      # for "feed" items: the food.FoodKind to stash on --stash


CATALOG: list[ShopItem] = [
    ShopItem("ration", "Food Ration", 180,
             "Restore some hunger (feed the pet)", "feed", 25.0,
             food_id="squid"),
    ShopItem("feast", "Salvage Feast", 280,
             "A big meal — restore lots of hunger", "feed", 60.0,
             food_id="cell"),
    ShopItem("energy_snack", "Energy Snack", 300,
             "Restore energy", "energy", 35.0),
    ShopItem("repair_kit", "Repair Kit", 360,
             "Restore health", "health", 40.0),
    ShopItem("lure", "Monster Lure", 450,
             "Consumable: boosts encounter rate (sets a lure flag)", "lure", 1.0),
    ShopItem("reroll_token", "Gear Reroll Token", 880,
             "Reroll an UNEQUIPPED item's rarity/stats", "reroll", 1.0),
    # --- endgame sink: a long-horizon scrap purpose (a session earns ~2000) ---
    ShopItem("skin_goldfin", "Golden Fin Skin", 5000,
             "Cosmetic: a permanent gold skin for your pet (bragging rights)",
             "cosmetic", 1.0),
]

_BY_ID = {it.id: it for it in CATALOG}


def food_kind_for(item: ShopItem):
    """Resolve the :class:`game.food.FoodKind` a "feed" shop item stashes as.

    Prefers the item's explicit ``food_id``; otherwise falls back to the food
    whose restore value is nearest the item's hunger magnitude. Returns ``None``
    for non-feed items or when the food catalogue can't satisfy the lookup."""
    if item.effect != "feed":
        return None
    from . import food as food_mod
    if item.food_id:
        fk = food_mod.get(item.food_id)
        if fk is not None:
            return fk
    kinds = food_mod.all_kinds()
    if not kinds:
        return None
    return min(kinds, key=lambda fk: abs(fk.restore - item.magnitude))


class Shop:
    def __init__(self, cfg=None):
        self.cfg = cfg

    def list_items(self) -> list[ShopItem]:
        return list(CATALOG)

    def get(self, item_id: str) -> ShopItem | None:
        return _BY_ID.get(item_id)

    def buy(self, wallet: Wallet, item_id: str, inv=None, state=None,
            target_item_id: str | None = None, rng=None,
            stash: bool = False, larder=None) -> tuple[bool, str]:
        """Purchase `item_id`, charging `wallet` and applying the effect.

        Returns (ok, message). Never raises. On insufficient funds or a
        non-applicable effect (e.g. reroll with no eligible item) nothing is
        charged. `target_item_id` selects which inventory item a reroll touches.

        When ``stash`` is set for a "feed" item, the bought food is deposited
        into ``larder`` (a :class:`game.larder.Larder`) as a
        :class:`game.food.FoodKind` instead of instantly restoring hunger; the
        pet's hunger is left unchanged. A full larder is treated like any other
        non-applicable effect: nothing is charged.
        """
        item = _BY_ID.get(item_id)
        if item is None:
            return False, f"No such item: {item_id}"
        if not wallet.can_afford(item.cost):
            return (False,
                    f"Not enough scrap for {item.name} "
                    f"(need {item.cost}, have {wallet.scrap})")
        if stash:
            ok, msg = self._stash(item, larder)
        else:
            ok, msg = self._apply(item, inv=inv, state=state,
                                  target_item_id=target_item_id, rng=rng)
        if not ok:
            return False, msg          # effect couldn't apply -> no charge
        wallet.spend(item.cost)
        return True, f"{msg} (-{item.cost} scrap, {wallet.scrap} left)"

    # -- stash (deposit feed items into the larder) ---------------------------
    @staticmethod
    def _stash(item: ShopItem, larder) -> tuple[bool, str]:
        if item.effect != "feed":
            return False, f"{item.name} can't be stashed in the larder"
        if larder is None:
            return False, "No larder to stash into"
        fk = food_kind_for(item)
        if fk is None:
            return False, f"Nothing to stash for {item.name}"
        stored = larder.add(fk.id, 1)
        if stored <= 0:
            return False, "Larder is full"
        return True, f"Stashed {fk.name} in the larder"

    # -- effect dispatch ------------------------------------------------------
    def _apply(self, item: ShopItem, inv=None, state=None,
               target_item_id: str | None = None, rng=None) -> tuple[bool, str]:
        eff = item.effect
        if eff in ("feed", "energy", "health"):
            return self._apply_stat(eff, item.magnitude, state)
        if eff == "lure":
            return self._apply_lure(state)
        if eff == "cosmetic":
            return self._apply_cosmetic(item, state)
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
    def _apply_cosmetic(item: ShopItem, state) -> tuple[bool, str]:
        if state is None:
            return False, "No pet to wear that"
        # record the unlocked skin on the pet; refuse (no charge) if already owned
        skins = set(getattr(state, "skins", None) or [])
        if item.id in skins:
            return False, f"{item.name} already unlocked"
        skins.add(item.id)
        setattr(state, "skins", sorted(skins))
        return True, f"Unlocked {item.name}"

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
