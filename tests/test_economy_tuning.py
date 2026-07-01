"""Economy & balance retuning (gameplay-review "Economy & Balance").

Covers the retuned shop prices, the new endgame scrap sink, the OPEN-network
earn helper, and the retuned Config defaults. These lock in the intended
balance so a stray edit can't silently unwind it.
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flippergotchi.config import Config
from flippergotchi.game import shop as shop_mod
from flippergotchi.pet.state import PetState


def _tmp(name):
    return os.path.join(tempfile.mkdtemp(), name)


def _wallet(scrap):
    w = shop_mod.Wallet(_tmp("w.json"))
    w.earn(scrap)
    return w


# --- retuned catalogue prices ------------------------------------------------
def test_catalog_prices_retuned():
    by_id = shop_mod._BY_ID
    assert by_id["ration"].cost == 180
    assert by_id["feast"].cost == 280
    assert by_id["energy_snack"].cost == 300
    assert by_id["repair_kit"].cost == 360
    assert by_id["lure"].cost == 450
    assert by_id["reroll_token"].cost == 880


def test_prices_raised_over_legacy():
    # every legacy consumable got meaningfully dearer (>= ~2x the old values)
    legacy = {"ration": 60, "feast": 140, "energy_snack": 90,
              "repair_kit": 110, "lure": 150, "reroll_token": 220}
    for iid, old in legacy.items():
        assert shop_mod._BY_ID[iid].cost >= old * 2


# --- endgame sink ------------------------------------------------------------
def test_endgame_sink_item_exists_and_is_expensive():
    sinks = [it for it in shop_mod.CATALOG if 2000 <= it.cost <= 8000]
    assert sinks, "expected at least one 2000-8000 scrap endgame sink"
    skin = shop_mod._BY_ID["skin_goldfin"]
    assert skin.cost == 5000
    assert skin.effect == "cosmetic"


def test_buy_cosmetic_unlocks_skin_and_charges():
    w = _wallet(6000)
    shop = shop_mod.Shop()
    st = PetState()
    ok, msg = shop.buy(w, "skin_goldfin", state=st)
    assert ok, msg
    assert "skin_goldfin" in getattr(st, "skins", [])
    assert w.scrap == 6000 - 5000


def test_buy_cosmetic_twice_refused_no_double_charge():
    w = _wallet(11000)
    shop = shop_mod.Shop()
    st = PetState()
    ok1, _ = shop.buy(w, "skin_goldfin", state=st)
    assert ok1 and w.scrap == 6000
    ok2, msg = shop.buy(w, "skin_goldfin", state=st)
    assert not ok2 and "already" in msg.lower()
    assert w.scrap == 6000  # not charged again


def test_cosmetic_unaffordable_not_charged():
    w = _wallet(1000)
    shop = shop_mod.Shop()
    st = PetState()
    ok, msg = shop.buy(w, "skin_goldfin", state=st)
    assert not ok and "Not enough scrap" in msg
    assert w.scrap == 1000


# --- earn rules: OPEN network pays catch-tier, not crack-tier ----------------
def test_scrap_for_open_is_catch_tier():
    v = shop_mod.scrap_for_open()
    assert v == 18
    assert v == shop_mod.SCRAP_PER_OPEN
    # catch-tier: well below a real crack, near a plain catch
    assert v < shop_mod.scrap_for_crack()
    assert v <= 20 and v >= shop_mod.scrap_for_catch()


def test_scrap_per_catch_lowered():
    assert shop_mod.SCRAP_PER_CATCH == 8
    assert shop_mod.scrap_for_catch() == 8


def test_crack_still_top_reward():
    assert shop_mod.scrap_for_crack() == 120
    assert shop_mod.scrap_for_crack() > shop_mod.scrap_for_open()


# --- retuned Config defaults -------------------------------------------------
def test_config_forage_defaults_retuned():
    cfg = Config()
    assert cfg.forage_food_per_m == 0.01
    assert cfg.forage_auto_eat_hunger == 80.0
    assert cfg.xp_per_snack == 0.5
