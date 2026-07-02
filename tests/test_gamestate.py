from __future__ import annotations

import json
import os

import pytest

from flippergotchi import persistence
from flippergotchi.config import Config
from flippergotchi.game.achievements import AchievementBook
from flippergotchi.game.bestiary import Bestiary
from flippergotchi.game.equipment import Inventory, Item
from flippergotchi.game.larder import Larder
from flippergotchi.game.ledger import Ledger
from flippergotchi.game.quests import QuestLog, _TEMPLATES
from flippergotchi.game.shop import Wallet
from flippergotchi.gamestate import GameState
from flippergotchi.pet.state import PetState

FILES = ("bestiary.json", "ledger.json", "inventory.json", "quests.json",
         "state.json", "wallet.json", "achievements.json", "larder.json",
         "prefs.json", "peers.json")


def _cfg(tmp_path):
    p = lambda name: str(tmp_path / name)  # noqa: E731
    return Config(
        bestiary_path=p("bestiary.json"),
        ledger_path=p("ledger.json"),
        inventory_path=p("inventory.json"),
        quests_path=p("quests.json"),
        state_path=p("state.json"),
        wallet_path=p("wallet.json"),
        achievements_path=p("achievements.json"),
        larder_path=p("larder.json"),
        prefs_path=p("prefs.json"),
        peers_path=p("peers.json"),
    )


def test_attributes_have_right_types(tmp_path):
    gs = GameState(_cfg(tmp_path))
    assert isinstance(gs.dex, Bestiary)
    assert isinstance(gs.ledger, Ledger)
    assert isinstance(gs.inv, Inventory)
    assert isinstance(gs.quests, QuestLog)
    assert isinstance(gs.state, PetState)
    assert isinstance(gs.wallet, Wallet)
    assert isinstance(gs.book, AchievementBook)
    assert isinstance(gs.larder, Larder)
    assert isinstance(gs.prefs, dict)
    assert isinstance(gs.peers, dict)


def test_save_writes_all_files(tmp_path):
    gs = GameState(_cfg(tmp_path))
    for name in FILES:
        assert not (tmp_path / name).exists(), f"{name} written before save()"
    gs.save()
    for name in FILES:
        assert (tmp_path / name).exists(), f"{name} not written by save()"
        with open(tmp_path / name) as f:
            json.load(f)  # every file must be valid JSON


def test_paths_come_from_cfg_and_round_trip(tmp_path):
    cfg = _cfg(tmp_path)
    gs = GameState(cfg)
    gs.state.name = "Sharky"
    gs.state.level = 4
    gs.wallet.earn(25)
    gs.prefs["battle_warning_ack"] = True
    gs.peers["aa:bb"] = {"name": "Mate"}
    gs.save()
    # reload each store from the cfg path independently of GameState
    assert persistence.load(cfg.state_path).name == "Sharky"
    assert persistence.load(cfg.state_path).level == 4
    assert Wallet(cfg.wallet_path).scrap == 25
    with open(cfg.prefs_path) as f:
        assert json.load(f)["battle_warning_ack"] is True
    with open(cfg.peers_path) as f:
        assert json.load(f)["aa:bb"] == {"name": "Mate"}
    # and a fresh GameState sees the same data
    gs2 = GameState(cfg)
    assert gs2.state.name == "Sharky"
    assert gs2.wallet.scrap == 25
    assert gs2.prefs["battle_warning_ack"] is True


def test_context_manager_saves_on_clean_exit(tmp_path):
    cfg = _cfg(tmp_path)
    with GameState(cfg) as gs:
        assert gs is not None
        gs.state.name = "CtxPet"
        gs.wallet.earn(7)
    for name in FILES:
        assert (tmp_path / name).exists(), f"{name} not saved on clean exit"
    assert persistence.load(cfg.state_path).name == "CtxPet"
    assert Wallet(cfg.wallet_path).scrap == 7


def test_context_manager_does_not_save_on_exception(tmp_path):
    cfg = _cfg(tmp_path)
    with pytest.raises(RuntimeError):
        with GameState(cfg) as gs:
            gs.state.name = "DoomedPet"
            gs.wallet.earn(999)
            raise RuntimeError("boom mid-command")
    for name in FILES:
        assert not (tmp_path / name).exists(), \
            f"{name} written despite exception"


def test_context_manager_enter_returns_self(tmp_path):
    gs = GameState(_cfg(tmp_path))
    assert gs.__enter__() is gs
    # __exit__ must not swallow exceptions
    assert gs.__exit__(RuntimeError, RuntimeError("x"), None) is False


def test_state_reassignment_is_saved(tmp_path):
    """Commands sometimes reload/replace the PetState; save() must persist
    whatever is currently bound to .state."""
    cfg = _cfg(tmp_path)
    gs = GameState(cfg)
    gs.state = PetState(name="Replacement", level=9)
    gs.save()
    loaded = persistence.load(cfg.state_path)
    assert loaded.name == "Replacement"
    assert loaded.level == 9


def test_larder_uses_cfg_capacity(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.larder_capacity = 3
    gs = GameState(cfg)
    assert gs.larder.capacity == 3


def test_all_ten_stores_round_trip_content(tmp_path):
    """Mutate the CONTENT of every one of the ten stores, save, then reload a
    FRESH GameState and assert each mutation survived -- not just that the
    files exist."""
    from flippergotchi.game import monsters

    cfg = _cfg(tmp_path)
    gs = GameState(cfg)

    # dex: a caught monster
    m = monsters.from_ap({"type": "ap", "bssid": "AA:BB:CC:00:11:22",
                          "ssid": "RoundTripNet", "encryption": "open",
                          "band": "2.4GHz", "clients": 1, "signal": -50})
    m.captured = True
    gs.dex.add(m)

    # ledger: a battle outcome
    gs.ledger.record(m, "cracked", via="dictionary")

    # inv: a gear item (with a set tag so we exercise the full field set)
    item = Item(id="itm-rt", name="Round Trip Shiv", slot="weapon",
                rarity="rare", power=11, bonus_stat="atk", bonus_val=2.5,
                set="reef")
    gs.inv.add(item)

    # quests: roll a day + advance a metric
    gs.quests.roll("2026-06-16", n=len(_TEMPLATES))
    tracked = gs.quests.active()[0].metric
    gs.quests.record(tracked, 1)

    # wallet: scrap balance
    gs.wallet.earn(42)

    # book: an unlocked badge
    gs.book.check({"catches": 999})  # unlocks catch-count badges
    unlocked_before = {b.id for b in gs.book.unlocked()}
    assert unlocked_before, "test setup: expected at least one badge unlocked"

    # larder: stashed food
    gs.larder.add("berry", 3)

    # state: pet content
    gs.state.name = "RoundTripPet"
    gs.state.level = 7
    gs.state.lures = 2

    # prefs + peers dicts
    gs.prefs["battle_warning_ack"] = True
    gs.peers["de:ad:be:ef"] = {"name": "Buddy", "level": 5}

    gs.save()

    # -- reload a completely fresh facade and verify every store's content ----
    gs2 = GameState(cfg)
    assert gs2.dex.get("RoundTripNet") is not None
    assert gs2.dex.get("RoundTripNet").captured is True
    assert gs2.ledger.counts()["win"] == 1
    reloaded_item = gs2.inv.items["itm-rt"]
    assert reloaded_item.name == "Round Trip Shiv"
    assert reloaded_item.set == "reef"
    assert reloaded_item.bonus_val == 2.5
    assert any(q.metric == tracked and q.progress >= 1 for q in gs2.quests.active())
    assert gs2.wallet.scrap == 42
    assert {b.id for b in gs2.book.unlocked()} == unlocked_before
    assert gs2.larder.items.get("berry") == 3
    assert gs2.state.name == "RoundTripPet"
    assert gs2.state.level == 7
    assert gs2.state.lures == 2
    assert gs2.prefs["battle_warning_ack"] is True
    assert gs2.peers["de:ad:be:ef"] == {"name": "Buddy", "level": 5}
