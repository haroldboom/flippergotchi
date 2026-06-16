"""Digimon-style PvP duels between two Flippergotchis over Bluetooth.

When another Flippergotchi is detected advertising over BLE, you can challenge
it. The duel is resolved from each fighter's power (level + collection strength)
with a dose of luck. Stakes: the loser forfeits some of their captured
handshakes to the winner ("monster theft").

Peer discovery + the actual BLE transport are stubbed (see core/bluetooth.py);
this module is the pure, testable game logic so it runs in simulation today.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .elements import advantage_multiplier, matchup_note

# how many handshakes the loser forfeits, as a fraction of their captured pool
DEFAULT_STAKE_FRAC = 0.20
MIN_STAKE = 1
MAX_STAKE = 10


@dataclass
class Fighter:
    """A snapshot of a Flippergotchi for a duel (yours, or a detected peer)."""
    name: str
    level: int = 1
    handshakes: int = 0          # size of the capture pool (the prize pool)
    health: float = 100.0
    happiness: float = 70.0
    gear: float = 0.0            # equipped-gear power bonus
    element: str = "Aether"      # for type-advantage
    addr: str = ""               # BLE address, for peers

    def power(self) -> float:
        """Battle power: level dominates; collection, gear, condition add weight."""
        return (self.level * 10.0
                + self.handshakes * 0.5
                + self.gear
                + self.health * 0.2
                + self.happiness * 0.1)


@dataclass
class DuelResult:
    winner: str
    loser: str
    you_won: bool
    stake: int                   # handshakes transferred loser -> winner
    your_power: float
    their_power: float
    your_roll: float
    their_roll: float
    log: list = field(default_factory=list)


def win_chance(you: Fighter, them: Fighter) -> float:
    """Probability you win, from the power ratio (never a sure thing)."""
    a, b = you.power(), them.power()
    p = a / (a + b) if (a + b) > 0 else 0.5
    return max(0.08, min(0.92, p))   # upsets are always possible


def _stake(loser: Fighter, cfg=None) -> int:
    frac = getattr(cfg, "duel_stake_frac", DEFAULT_STAKE_FRAC) if cfg else DEFAULT_STAKE_FRAC
    n = int(loser.handshakes * frac)
    return max(MIN_STAKE, min(MAX_STAKE, n)) if loser.handshakes > 0 else 0


def duel(you: Fighter, them: Fighter, cfg=None, rng=random) -> DuelResult:
    p = win_chance(you, them)
    # Elemental type advantage: scale your odds by your edge vs theirs.
    atk = advantage_multiplier(you.element, them.element)   # ~1.25 / 1.0 / 0.8
    dfn = advantage_multiplier(them.element, you.element)
    p = (p * atk) / (p * atk + (1 - p) * dfn)               # re-normalize
    p = max(0.08, min(0.92, p))                             # keep upsets possible
    your_roll = rng.random()
    you_won = your_roll < p
    winner, loser = (you, them) if you_won else (them, you)
    stake = _stake(loser, cfg)
    log = [
        f"{you.name} ({you.element} Lv{you.level}, pow {you.power():.0f}) challenges "
        f"{them.name} ({them.element} Lv{them.level}, pow {them.power():.0f})!",
        f"win chance {p*100:.0f}% -- " + ("YOU WIN!" if you_won else "you lost..."),
    ]
    note = matchup_note(you.element, them.element)
    if note != "neutral":
        log.insert(1, f"type matchup: {you.element} vs {them.element} -> {note} for you")
    if stake:
        log.append(f"{winner.name} seizes {stake} handshake(s) from {loser.name}.")
    else:
        log.append(f"{loser.name} had no handshakes to forfeit.")
    return DuelResult(
        winner=winner.name, loser=loser.name, you_won=you_won, stake=stake,
        your_power=you.power(), their_power=them.power(),
        your_roll=your_roll, their_roll=1 - your_roll, log=log,
    )


def apply_result(state, res: DuelResult) -> None:
    """Settle the stake against your live pet state (handshakes pool)."""
    if res.stake <= 0:
        return
    if res.you_won:
        state.handshakes += res.stake
    else:
        state.handshakes = max(0, state.handshakes - res.stake)
