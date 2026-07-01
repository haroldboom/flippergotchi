"""Single facade over every persistent store.

Commands historically constructed 4-5 store objects each and had to remember
to call ``.save()`` on every one at every exit path.  ``GameState`` loads all
of them once and persists them together, so a command can do::

    with GameState(cfg) as gs:
        gs.state.xp += 5
        gs.wallet.earn(10)
    # everything saved on clean exit; nothing written if the body raised

This is pure composition of the existing store classes -- construction and
save mirror commands.py exactly, so on-disk JSON formats are unchanged.
"""
from __future__ import annotations

from . import persistence
from . import prefs as prefs_mod
from .game.achievements import AchievementBook
from .game.bestiary import Bestiary
from .game.equipment import Inventory
from .game.larder import Larder
from .game.ledger import Ledger
from .game.quests import QuestLog
from .game.shop import Wallet


class GameState:
    """Every persistent store, loaded once and saved atomically together.

    Attributes
    ----------
    dex     : Bestiary        -- caught-monster records (cfg.bestiary_path)
    ledger  : Ledger          -- battle outcome log     (cfg.ledger_path)
    inv     : Inventory       -- gear items             (cfg.inventory_path)
    quests  : QuestLog        -- daily/weekly quests    (cfg.quests_path)
    state   : PetState        -- the pet itself         (cfg.state_path)
    wallet  : Wallet          -- scrap currency         (cfg.wallet_path)
    book    : AchievementBook -- badges                 (cfg.achievements_path)
    larder  : Larder          -- stashed food           (cfg.larder_path)
    prefs   : dict            -- consent/warning prefs  (cfg.prefs_path)
    peers   : dict            -- known BLE peers        (cfg.peers_path)
    """

    def __init__(self, cfg):
        self.cfg = cfg
        self.dex = Bestiary(cfg.bestiary_path)
        self.ledger = Ledger(cfg.ledger_path)
        self.inv = Inventory(cfg.inventory_path)
        self.quests = QuestLog(cfg.quests_path)
        self.state = persistence.load(cfg.state_path)
        self.wallet = Wallet(getattr(cfg, "wallet_path",
                                     "~/.flippergotchi/wallet.json"))
        self.book = AchievementBook(getattr(cfg, "achievements_path",
                                            "~/.flippergotchi/achievements.json"))
        self.larder = Larder(getattr(cfg, "larder_path",
                                     "~/.flippergotchi/larder.json"),
                             getattr(cfg, "larder_capacity", 20))
        self.prefs = prefs_mod.load(cfg.prefs_path)
        self.peers = prefs_mod.load(cfg.peers_path)

    def save(self) -> None:
        """Persist every store, exactly as each is saved today."""
        self.dex.save()
        self.ledger.save()
        self.inv.save()
        self.quests.save()
        persistence.save(self.cfg.state_path, self.state)
        self.wallet.save()
        self.book.save()
        self.larder.save()
        prefs_mod.save(self.cfg.prefs_path, self.prefs)
        prefs_mod.save(self.cfg.peers_path, self.peers)

    # -- context manager: save only on clean exit ---------------------------
    def __enter__(self) -> "GameState":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is None:
            self.save()
        return False  # never swallow exceptions
