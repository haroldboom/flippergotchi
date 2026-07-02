"""--stash for shop feed items: deposit into the Larder instead of feeding.

A feed item bought with stash lands in the larder as a food.FoodKind and leaves
hunger untouched; without stash it instant-applies as before; a full larder
refuses the purchase (nothing charged).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flippergotchi.game import food as food_mod
from flippergotchi.game import shop as shop_mod
from flippergotchi.game.larder import Larder
from flippergotchi.pet.state import PetState


def _wallet(tmp_file, scrap):
    w = shop_mod.Wallet(tmp_file("w.json"))
    w.earn(scrap)
    return w


# --- food mapping ------------------------------------------------------------
def test_food_kind_for_feed_items_resolves():
    ration = shop_mod._BY_ID["ration"]
    feast = shop_mod._BY_ID["feast"]
    assert shop_mod.food_kind_for(ration).id == "squid"
    assert shop_mod.food_kind_for(feast).id == "cell"
    # both ids must exist in the food catalogue
    assert food_mod.get("squid") is not None
    assert food_mod.get("cell") is not None


def test_food_kind_for_nonfeed_is_none():
    assert shop_mod.food_kind_for(shop_mod._BY_ID["lure"]) is None
    assert shop_mod.food_kind_for(shop_mod._BY_ID["repair_kit"]) is None


# --- stash deposits into the larder, hunger unchanged ------------------------
def test_stash_adds_to_larder_and_leaves_hunger(tmp_file):
    w = _wallet(tmp_file, 200)
    shop = shop_mod.Shop()
    st = PetState(hunger=80.0)
    larder = Larder(tmp_file("l.json"), capacity=20)
    ok, msg = shop.buy(w, "ration", state=st, stash=True, larder=larder)
    assert ok, msg
    assert st.hunger == 80.0                 # hunger untouched
    assert larder.counts().get("squid") == 1  # food deposited
    assert w.scrap == 200 - shop_mod._BY_ID["ration"].cost


def test_stash_feast_deposits_its_food_kind(tmp_file):
    w = _wallet(tmp_file, 300)
    shop = shop_mod.Shop()
    st = PetState(hunger=50.0)
    larder = Larder(tmp_file("l.json"), capacity=20)
    ok, _ = shop.buy(w, "feast", state=st, stash=True, larder=larder)
    assert ok
    assert larder.counts().get("cell") == 1
    assert st.hunger == 50.0


# --- without stash: hunger drops as before -----------------------------------
def test_no_stash_feeds_as_before(tmp_file):
    w = _wallet(tmp_file, 200)
    shop = shop_mod.Shop()
    st = PetState(hunger=80.0)
    larder = Larder(tmp_file("l.json"), capacity=20)
    ration = shop_mod._BY_ID["ration"]
    ok, _ = shop.buy(w, "ration", state=st, larder=larder)
    assert ok
    assert st.hunger == 80.0 - ration.magnitude  # hunger dropped
    assert larder.total() == 0                   # nothing stashed


# --- capacity is respected ---------------------------------------------------
def test_stash_respects_larder_capacity(tmp_file):
    w = _wallet(tmp_file, 1000)
    shop = shop_mod.Shop()
    st = PetState(hunger=80.0)
    larder = Larder(tmp_file("l.json"), capacity=1)
    ok1, _ = shop.buy(w, "ration", state=st, stash=True, larder=larder)
    assert ok1 and larder.total() == 1
    spent = w.scrap
    # larder now full -> refused, nothing charged, hunger untouched
    ok2, msg = shop.buy(w, "ration", state=st, stash=True, larder=larder)
    assert not ok2
    assert "full" in msg.lower()
    assert larder.total() == 1
    assert w.scrap == spent          # no charge
    assert st.hunger == 80.0


def test_stash_without_larder_refused_no_charge(tmp_file):
    w = _wallet(tmp_file, 200)
    shop = shop_mod.Shop()
    st = PetState(hunger=80.0)
    ok, msg = shop.buy(w, "ration", state=st, stash=True, larder=None)
    assert not ok
    assert w.scrap == 200
    assert st.hunger == 80.0


def test_stash_nonfeed_item_refused(tmp_file):
    w = _wallet(tmp_file, 500)
    shop = shop_mod.Shop()
    larder = Larder(tmp_file("l.json"), capacity=20)
    ok, msg = shop.buy(w, "energy_snack", stash=True, larder=larder)
    assert not ok
    assert larder.total() == 0
    assert w.scrap == 500
