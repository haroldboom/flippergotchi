"""Progression depth: achievements, scrap shop, and gear-set bonuses.

Covers threshold-crossing unlocks (and no re-grant), shop buy success /
insufficient-funds / effect application, and gear-set bonus tiers (2/4/5 pcs).
"""
from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flippergotchi.game import achievements as ach
from flippergotchi.game import equipment as eq
from flippergotchi.game import gearsets
from flippergotchi.game import shop as shop_mod
from flippergotchi.pet.state import PetState


# --- achievements ------------------------------------------------------------
def test_achievement_unlocks_on_threshold_crossing(tmp_file):
    book = ach.AchievementBook(tmp_file("a.json"))
    assert book.check({"catches": 0}) == []
    newly = book.check({"catches": 1})
    ids = {b.id for b in newly}
    assert "first_catch" in ids
    assert book.is_unlocked("first_catch")


def test_achievement_not_regranted(tmp_file):
    book = ach.AchievementBook(tmp_file("a.json"))
    book.check({"catches": 10})          # first_catch + catch_10
    again = book.check({"catches": 60})  # only NEW ones (catch_50) this time
    assert {b.id for b in again} == {"catch_50"}
    assert book.check({"catches": 60}) == []   # nothing new at the same level


def test_achievement_rewards_returned(tmp_file):
    book = ach.AchievementBook(tmp_file("a.json"))
    newly = book.check({"catches": 1})
    badge = next(b for b in newly if b.id == "first_catch")
    assert badge.reward.get("scrap", 0) > 0


def test_achievement_categorical_and_loadout_metrics(tmp_file):
    book = ach.AchievementBook(tmp_file("a.json"))
    out = book.check({"stage": "legend", "equipped_slots": 5})
    ids = {b.id for b in out}
    assert "evolve_to_legend" in ids and "full_loadout" in ids
    # a non-legend stage never trips the legend badge
    book2 = ach.AchievementBook(tmp_file("a2.json"))
    assert all(b.id != "evolve_to_legend" for b in book2.check({"stage": "teen"}))


def test_build_stats_sources_cracks_from_ledger(tmp_file):
    # foundation fix: cracks come from the Ledger (the agent loop used to pass 0,
    # so crack badges could never unlock during normal play)
    from flippergotchi.game import ledger as ledger_mod
    led = ledger_mod.Ledger(tmp_file("l.json"))
    led.records.append({"result": "win"})
    led.records.append({"result": "win"})
    stats = ach.build_stats(PetState(level=3), dex=None, inv=None, ledger=led)
    assert stats["cracks"] == 2
    assert stats["level"] == 3


def test_quests_done_capstone_from_questlog(tmp_file):
    # the cross-system tie: quest activity (lifetime_done) unlocks achievements
    class FakeQ:
        lifetime_done = 10
        streak = 0
    stats = ach.build_stats(PetState(), quests=FakeQ())
    assert stats["quests_done"] == 10
    book = ach.AchievementBook(tmp_file("a.json"))
    assert any(b.id == "quest_10" for b in book.check(stats))


def test_streak_badge_unlocks(tmp_file):
    class FakeQ:
        lifetime_done = 0
        streak = 7
    book = ach.AchievementBook(tmp_file("a.json"))
    stats = ach.build_stats(PetState(), quests=FakeQ())
    assert any(b.id == "streak_7" for b in book.check(stats))


def test_hidden_badge_masked_until_unlocked():
    b = ach.Badge("secret_x", "Secret", "hidden test badge", "catches", 1,
                  hidden=True)
    assert b.hidden
    assert ach.display_name(b, unlocked=False) != b.name      # masked while locked
    assert ach.display_name(b, unlocked=True) == b.name        # revealed once earned


def test_badge_tiers_and_new_metric_series():
    assert ach.get("catch_100").tier == "gold"
    assert ach.get("tame_10").metric == "tames"               # phase-3 metric wired
    assert ach.get("legend_3").metric == "legendary_kills"


def test_tame_and_legendary_badges_unlock(tmp_file):
    book = ach.AchievementBook(tmp_file("a.json"))
    assert any(b.id == "tame_10" for b in book.check({"tames": 10}))
    book2 = ach.AchievementBook(tmp_file("a2.json"))
    assert any(b.id == "legend_3" for b in book2.check({"legendary_kills": 3}))


def test_progress_readout():
    assert ach.progress(ach.get("catch_50"), {"catches": 12}) == (12, 50)


def test_gold_capstone_mints_gear(tmp_file):
    from flippergotchi.config import Config
    from flippergotchi.game import equipment as eq
    from flippergotchi.game.shop import Wallet
    book = ach.AchievementBook(tmp_file("a.json"))
    w = Wallet(tmp_file("w.json"))
    inv = eq.Inventory(tmp_file("i.json"))
    cfg, st = Config(), PetState(level=20)
    newly = ach.grant_reward(book, {"cracks": 50}, st, cfg, w, inv)   # crack_50 = gold+gear
    assert any(b.id == "crack_50" for b in newly)
    assert len(inv.all()) >= 1                                 # a gear item was minted


def test_grant_reward_pays_scrap_once(tmp_file):
    # the single reward path: pays a badge's scrap exactly once, never on re-check
    from flippergotchi.config import Config
    from flippergotchi.game.shop import Wallet
    book = ach.AchievementBook(tmp_file("a.json"))
    w = Wallet(tmp_file("w.json"))
    cfg, st = Config(), PetState()
    newly = ach.grant_reward(book, {"catches": 1}, st, cfg, w)
    assert any(b.id == "first_catch" for b in newly)
    assert w.scrap == 50                       # first_catch reward
    again = ach.grant_reward(book, {"catches": 1}, st, cfg, w)
    assert all(b.id != "first_catch" for b in again)
    assert w.scrap == 50                       # not paid twice on re-check


def test_achievement_persistence_roundtrip(tmp_file):
    p = tmp_file("a.json")
    book = ach.AchievementBook(p)
    book.check({"cracks": 1})
    book.save()
    reloaded = ach.AchievementBook(p)
    assert reloaded.is_unlocked("crack_1")
    assert reloaded.check({"cracks": 1}) == []   # still not re-granted after reload


def test_achievement_views(tmp_file):
    book = ach.AchievementBook(tmp_file("a.json"))
    book.check({"catches": 1})
    assert any(b.id == "first_catch" for b in book.unlocked())
    assert all(b.id != "first_catch" for b in book.locked())
    assert len(book.all()) == len(ach.CATALOG)


# --- shop / wallet -----------------------------------------------------------
def test_wallet_earn_and_persist(tmp_file):
    p = tmp_file("w.json")
    w = shop_mod.Wallet(p)
    w.earn(200)
    w.earn(-50)                  # negatives ignored
    assert w.scrap == 200
    w.save()
    assert shop_mod.Wallet(p).scrap == 200


def test_earn_rule_helpers():
    assert shop_mod.scrap_for_crack() > 0
    assert shop_mod.scrap_for_duel_win() > 0
    assert shop_mod.scrap_for_catch() > 0
    assert shop_mod.scrap_for_walk(1000) == shop_mod.SCRAP_PER_KM
    assert shop_mod.scrap_for_walk(0) == 0


def test_shop_buy_insufficient_funds(tmp_file):
    w = shop_mod.Wallet(tmp_file("w.json"))   # 0 scrap
    shop = shop_mod.Shop()
    st = PetState(hunger=80.0)
    ok, msg = shop.buy(w, "ration", state=st)
    assert ok is False and "Not enough scrap" in msg
    assert st.hunger == 80.0 and w.scrap == 0     # nothing changed


def test_shop_buy_feeds_and_charges(tmp_file):
    w = shop_mod.Wallet(tmp_file("w.json"))
    w.earn(500)
    shop = shop_mod.Shop()
    st = PetState(hunger=80.0)
    ration = shop.get("ration")
    ok, msg = shop.buy(w, "ration", state=st)
    assert ok is True
    assert st.hunger == 80.0 - ration.magnitude
    assert w.scrap == 500 - ration.cost


def test_shop_lure_sets_flag(tmp_file):
    w = shop_mod.Wallet(tmp_file("w.json"))
    w.earn(500)
    shop = shop_mod.Shop()
    st = PetState()
    ok, _ = shop.buy(w, "lure", state=st)
    assert ok and getattr(st, "lures", 0) == 1


def test_shop_reroll_replaces_unequipped_item(tmp_file):
    w = shop_mod.Wallet(tmp_file("w.json"))
    w.earn(1000)
    shop = shop_mod.Shop()
    inv = eq.Inventory(tmp_file("inv.json"))
    keep = inv.add(eq.Item("keep", "Tuned Helm", "helmet", "rare", 11))
    inv.equip("keep")
    rr = inv.add(eq.Item("rr", "Scuffed Crest", "fin", "common", 3))
    rng = random.Random(5)
    ok, msg = shop.buy(w, "reroll_token", inv=inv, target_item_id="rr", rng=rng)
    assert ok is True
    assert "rr" in inv.items and inv.items["rr"].slot == "fin"   # id + slot preserved
    assert inv.is_equipped("keep")                              # untouched


def test_shop_reroll_no_eligible_item_does_not_charge(tmp_file):
    w = shop_mod.Wallet(tmp_file("w.json"))
    w.earn(1000)
    shop = shop_mod.Shop()
    inv = eq.Inventory(tmp_file("inv.json"))
    inv.add(eq.Item("only", "Tuned Helm", "helmet", "rare", 11))
    inv.equip("only")            # the only item is equipped -> not rerollable
    ok, msg = shop.buy(w, "reroll_token", inv=inv)
    assert ok is False and w.scrap == 1000


def test_shop_unknown_item(tmp_file):
    w = shop_mod.Wallet(tmp_file("w.json"))
    w.earn(1000)
    ok, msg = shop_mod.Shop().buy(w, "does_not_exist")
    assert ok is False and w.scrap == 1000


# --- gear sets ---------------------------------------------------------------
def _set_items(set_name, n):
    """n equipped items all tagged with the same set, on distinct slots."""
    return [eq.Item(f"{set_name}-{i}", "X", eq.SLOTS[i], "rare", 11, set=set_name)
            for i in range(n)]


def test_set_bonus_needs_two_pieces():
    assert gearsets.set_bonus(_set_items("Reef Raider", 1)) == \
        {"power": 0, "atk": 0, "def": 0, "luck": 0}
    two = gearsets.set_bonus(_set_items("Reef Raider", 2))
    assert two["power"] > 0


def test_set_bonus_tiers_increase():
    two = gearsets.set_bonus(_set_items("Apex Predator", 2))["power"]
    four = gearsets.set_bonus(_set_items("Apex Predator", 4))["power"]
    five = gearsets.set_bonus(_set_items("Apex Predator", 5))["power"]
    assert two < four < five


def test_set_bonus_only_highest_threshold_per_set():
    # 5 pieces should give exactly the 5-pc tier, not 2+4+5 stacked
    five = gearsets.set_bonus(_set_items("Reef Raider", 5))
    assert five == {"power": 26, "atk": 8, "def": 0, "luck": 2}


def test_set_bonus_ignores_unknown_tags():
    items = [eq.Item("a", "X", "helmet", "rare", 11, set="Nonexistent Set"),
             eq.Item("b", "Y", "fin", "rare", 11, set="")]
    assert gearsets.set_bonus(items) == {"power": 0, "atk": 0, "def": 0, "luck": 0}


def test_inventory_pvp_power_folds_set_bonus(tmp_file):
    inv = eq.Inventory(tmp_file("inv.json"))
    for i in range(2):
        it = inv.add(eq.Item(f"r{i}", "X", eq.SLOTS[i], "rare", 11, set="Reef Raider"))
        inv.equip(it.id)
    assert inv.gear_power() == 22                       # unchanged meaning
    assert inv.pvp_power() == 22 + inv.set_bonus()["power"]
    assert inv.pvp_power() > inv.gear_power()


def test_describe_reports_active_set():
    txt = gearsets.describe(_set_items("Cyber Samurai", 4))
    assert "Cyber Samurai" in txt
    assert gearsets.describe([]) == "No set bonus active."


def test_item_set_field_back_compat():
    # legacy saves with no 'set' key still load, default ""
    it = eq.Item.from_dict({"id": "x", "name": "Old", "slot": "helmet",
                            "rarity": "rare", "power": 11})
    assert it.set == ""


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all good")
