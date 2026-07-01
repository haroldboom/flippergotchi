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
from . import moves as moves_mod

# how many handshakes the loser forfeits, as a fraction of their captured pool
DEFAULT_STAKE_FRAC = 0.20
MIN_STAKE = 1
MAX_STAKE = 10

# Turn-based duel tuning (override via cfg with getattr -- see config notes).
DEFAULT_TURN_CAP = 30        # hard stop; highest remaining HP wins on cap
BLEED_DMG = 4.0             # per-tick damage for a "bleed" status
CORRUPT_DMG = 6.0          # per-tick damage for a "corrupt" status (heavier)
DOT_TURNS = 3              # how many ticks bleed/corrupt last
SHIELD_TURNS = 2           # duration of a "shield" (def up)
BUFF_TURNS = 2             # duration of a "buff" (atk up)
SHIELD_MULT = 1.5          # def_mult while shielded (incoming dmg / 1.5)
BUFF_MULT = 1.35           # atk_mult while buffed (outgoing dmg * 1.35)
DRAIN_FRAC = 0.5           # fraction of damage healed by "drain" moves

# How equipped PvP stats (equipment.Inventory.stat_totals(): item bonuses +
# gear-set stat bonuses) feed the resolver. All zero-safe: a stat-less fighter
# behaves exactly like the pre-stat engine (same rng draws, same multipliers).
ATK_STAT_SCALE = 0.010     # atk_mult = 1 + ATK * this (outgoing damage up)
DEF_STAT_SCALE = 0.010     # def_mult = 1 + DEF * this (incoming damage down)
LUCK_CRIT_SCALE = 0.005    # crit_chance = LUCK * this ...
LUCK_CRIT_CAP = 0.35       # ...capped so crits stay spicy, not dominant
LUCK_INIT_WEIGHT = 2.0     # LUCK also weighs the initiative (first-move) roll


@dataclass
class Fighter:
    """A snapshot of a Flippergotchi for a duel (yours, or a detected peer)."""
    name: str
    level: int = 1
    handshakes: int = 0          # size of the capture pool (the prize pool)
    health: float = 100.0
    happiness: float = 70.0
    gear: float = 0.0            # equipped-gear power (use Inventory.pvp_power())
    element: str = "Aether"      # for type-advantage
    addr: str = ""               # BLE address, for peers
    satiety: float = 0.0         # well-fed buff: a small PvP-ONLY edge
    # Equipped PvP stat totals (equipment.Inventory.stat_totals(), which folds
    # in gear-set stat bonuses). Zero = the classic stat-less fighter.
    atk: float = 0.0             # scales outgoing damage
    defense: float = 0.0         # scales down incoming damage
    luck: float = 0.0            # feeds crit chance + initiative

    def power(self) -> float:
        """Battle power: level dominates; collection, gear, condition add weight.
        Satiety is a small PvP-only edge -- this is the ONLY place hunger-side
        state touches combat, and it lives in the duel (PvP) module, never in
        battle.py/cracking.py (which are deterministic and take no PetState)."""
        return (self.level * 10.0
                + self.handshakes * 0.5
                + self.gear
                + self.health * 0.2
                + self.happiness * 0.1
                + self.satiety * 0.15)


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


class _Combatant:
    """Mutable per-duel battle state wrapping a :class:`Fighter`.

    Holds live HP and status bookkeeping so the immutable-ish ``Fighter`` and
    the pure ``moves`` helpers stay clean. ``atk_mult`` / ``def_mult`` are read
    by ``moves.apply_move`` (via getattr) to fold buffs/shields into damage.
    """

    def __init__(self, fighter: Fighter):
        self.f = fighter
        self.name = fighter.name
        self.element = fighter.element
        self.max_hp = _hp_from_power(fighter.power())
        self.hp = self.max_hp
        # Baseline multipliers seeded from equipped ATK/DEF totals (gear item
        # bonuses + set bonuses). Buffs/shields stack ON TOP of these so gear
        # keeps mattering mid-fight; with zero stats this is the classic 1.0.
        self.base_atk = 1.0 + max(0.0, getattr(fighter, "atk", 0.0)) * ATK_STAT_SCALE
        self.base_def = 1.0 + max(0.0, getattr(fighter, "defense", 0.0)) * DEF_STAT_SCALE
        self.atk_mult = self.base_atk
        self.def_mult = self.base_def
        # LUCK -> crit chance, read by moves.apply_move via getattr.
        self.luck = max(0.0, getattr(fighter, "luck", 0.0))
        self.crit_chance = min(LUCK_CRIT_CAP, self.luck * LUCK_CRIT_SCALE)
        # status timers: keyword -> turns remaining
        self.dots: dict[str, int] = {}   # bleed / corrupt
        self.buff_turns = 0
        self.shield_turns = 0
        self.stunned = False

    # -- status application (called when a move procs an effect) -------------
    def gain(self, effect: str) -> None:
        if effect in ("bleed", "corrupt"):
            self.dots[effect] = max(self.dots.get(effect, 0), DOT_TURNS)
        elif effect == "buff":
            self.buff_turns = BUFF_TURNS
            self.atk_mult = self.base_atk * BUFF_MULT
        elif effect == "shield":
            self.shield_turns = SHIELD_TURNS
            self.def_mult = self.base_def * SHIELD_MULT
        elif effect == "stun":
            self.stunned = True

    # -- per-turn upkeep: tick DOTs + expire timers, return log lines --------
    def upkeep(self) -> list[str]:
        lines: list[str] = []
        for kind in ("bleed", "corrupt"):
            if self.dots.get(kind, 0) > 0:
                dmg = BLEED_DMG if kind == "bleed" else CORRUPT_DMG
                self.hp -= dmg
                self.dots[kind] -= 1
                lines.append(f"{self.name} takes {dmg:.0f} {kind} damage.")
        if self.buff_turns > 0:
            self.buff_turns -= 1
            if self.buff_turns == 0:
                self.atk_mult = self.base_atk
        if self.shield_turns > 0:
            self.shield_turns -= 1
            if self.shield_turns == 0:
                self.def_mult = self.base_def
        return lines


def _hp_from_power(power: float) -> float:
    """Map battle power onto a hit-point pool.

    HP scales with power so level/handshakes/gear/condition all stay relevant
    in PvP, with a floor so nobody is one-shot. (A Lv1 nobody sits ~60 HP, a
    decked-out fighter several hundred.)"""
    return max(40.0, 30.0 + power * 1.2)


def duel(you: Fighter, them: Fighter, cfg=None, rng=random) -> DuelResult:
    """Run a short turn-based duel and settle the stake.

    Each fighter has HP derived from :meth:`Fighter.power`. They alternate
    turns picking and applying moves (elemental STAB + type advantage, status
    effects) until one drops to 0 HP or the turn cap is hit -- on the cap the
    higher remaining HP (power on an exact tie) wins. Never raises.
    """
    try:
        return _run_duel(you, them, cfg, rng)
    except Exception as exc:  # pragma: no cover - safety net, duel must not raise
        # Degrade to the deterministic power tiebreak so callers always get a result.
        you_won = you.power() >= them.power()
        winner, loser = (you, them) if you_won else (them, you)
        stake = _stake(loser, cfg)
        return DuelResult(
            winner=winner.name, loser=loser.name, you_won=you_won, stake=stake,
            your_power=you.power(), their_power=them.power(),
            your_roll=0.5, their_roll=0.5,
            log=[f"duel aborted ({exc}); resolved by power.",
                 f"{winner.name} wins."],
        )


def _run_duel(you: Fighter, them: Fighter, cfg, rng) -> DuelResult:
    turn_cap = int(getattr(cfg, "duel_turn_cap", DEFAULT_TURN_CAP))
    a = _Combatant(you)
    b = _Combatant(them)

    note = matchup_note(you.element, them.element)
    log = [
        f"{you.name} ({you.element} Lv{you.level}, {a.max_hp:.0f} HP) challenges "
        f"{them.name} ({them.element} Lv{them.level}, {b.max_hp:.0f} HP)!",
    ]
    if note != "neutral":
        log.append(f"type matchup: {you.element} vs {them.element} -> {note} for you")

    # Initiative: stronger fighter tends to move first; equipped LUCK adds
    # weight to the roll (zero luck on both sides reduces to the pure power
    # ratio, preserving legacy seeded sequences).
    pa, pb = you.power(), them.power()
    wa = pa + a.luck * LUCK_INIT_WEIGHT
    wb = pb + b.luck * LUCK_INIT_WEIGHT
    you_first = rng.random() < (wa / (wa + wb) if (wa + wb) > 0 else 0.5)
    order = [(a, b), (b, a)] if you_first else [(b, a), (a, b)]

    turn = 0
    while a.hp > 0 and b.hp > 0 and turn < turn_cap:
        for attacker, defender in order:
            if a.hp <= 0 or b.hp <= 0:
                break
            log.extend(attacker.upkeep())
            if a.hp <= 0 or b.hp <= 0:
                break
            if attacker.stunned:
                attacker.stunned = False
                log.append(f"{attacker.name} is stunned and skips a turn!")
                continue
            move = moves_mod.pick_move(attacker, rng)
            adv = advantage_multiplier(attacker.element, defender.element)
            outcome = moves_mod.apply_move(attacker, defender, move, rng, adv)
            log.append(outcome["log_line"])
            if outcome["hit"]:
                defender.hp -= outcome["damage"]
                for eff in outcome["effects_applied"]:
                    if eff == "drain":
                        heal = round(outcome["damage"] * DRAIN_FRAC, 1)
                        attacker.hp = min(attacker.max_hp, attacker.hp + heal)
                        if heal > 0:
                            log.append(f"{attacker.name} recovers {heal:.0f} HP.")
                    else:
                        defender.gain(eff) if eff in ("bleed", "corrupt", "stun") \
                            else attacker.gain(eff)
        turn += 1

    # Decide the winner: KO, else highest remaining HP, else power tiebreak.
    if b.hp <= 0 < a.hp:
        you_won = True
    elif a.hp <= 0 < b.hp:
        you_won = False
    elif a.hp != b.hp:
        you_won = a.hp > b.hp
    else:
        you_won = you.power() >= them.power()

    if a.hp <= 0 or b.hp <= 0:
        ko = "them" if you_won else "you"
        log.append(f"KO! {(them if you_won else you).name} is down "
                   f"({'you win!' if you_won else 'you lost...'})")
    else:
        log.append(f"turn cap reached -- HP {a.hp:.0f} vs {b.hp:.0f}: "
                   + ("YOU WIN!" if you_won else "you lost..."))

    winner, loser = (you, them) if you_won else (them, you)
    stake = _stake(loser, cfg)
    if stake:
        log.append(f"{winner.name} seizes {stake} handshake(s) from {loser.name}.")
    else:
        log.append(f"{loser.name} had no handshakes to forfeit.")

    # your_roll/their_roll kept for API compat: normalised remaining-HP share.
    tot = a.hp + b.hp
    your_roll = (max(a.hp, 0.0) / tot) if tot > 0 else 0.5
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


# ---------------------------------------------------------------------------
# Loop-facing API: build fighters from live state and auto-resolve a duel.
# ---------------------------------------------------------------------------

def fighter_from_pet(state, inv=None, element: str | None = None) -> Fighter:
    """Snapshot your live pet (+ equipped inventory) into a duel Fighter.

    This is the ONE place player-side duel stats get assembled, so every
    caller (cmd_duel, the auto-loop) gets the same wiring:

    * ``gear`` comes from :meth:`Inventory.pvp_power` -- raw gear power PLUS
      gear-set power bonuses (never the bare ``gear_power()``).
    * ``atk``/``defense``/``luck`` come from :meth:`Inventory.stat_totals`
      (item stat rolls + set stat bonuses), seeding the resolver's damage
      multipliers, crit chance and initiative.
    * ``element`` is taken from the argument if given (normalised through the
      type chart's accepted spellings), else from ``state.element`` -- never
      hardcoded.
    """
    from .elements import ELEMENTS, normalize
    el = normalize(element) if element else None
    if el is None:
        raw = getattr(state, "element", "Aether")
        el = normalize(raw) or (raw if raw in ELEMENTS else "Aether")
    stats = inv.stat_totals() if inv is not None else {}
    return Fighter(
        name=getattr(state, "name", "you"),
        level=getattr(state, "level", 1),
        handshakes=getattr(state, "handshakes", 0),
        health=getattr(state, "health", 100.0),
        happiness=getattr(state, "happiness", 70.0),
        gear=float(inv.pvp_power()) if inv is not None else 0.0,
        element=el,
        satiety=getattr(state, "satiety", 0.0),
        atk=float(stats.get("atk", 0)),
        defense=float(stats.get("def", 0)),
        luck=float(stats.get("luck", 0)),
    )


def fighter_from_peer(peer: dict) -> Fighter:
    """Build the opposing Fighter from a detected-peer record (see agent.py's
    ``_peers``: name/addr/level/handshakes/gear_power/element)."""
    from .elements import ELEMENTS, normalize
    raw = peer.get("element", "Aether")
    el = normalize(raw) or (raw if raw in ELEMENTS else "Aether")
    gear = float(peer.get("gear_power", 0) or 0)
    # peers only advertise a single gear number; give them modest generic
    # stats from it so a geared peer isn't a pushover against your stat gear.
    return Fighter(
        name=peer.get("name", "?"),
        level=int(peer.get("level", 1) or 1),
        handshakes=int(peer.get("handshakes", 0) or 0),
        gear=gear,
        element=el,
        addr=peer.get("addr", ""),
        atk=gear * 0.5, defense=gear * 0.3, luck=gear * 0.2,
    )


@dataclass
class AutoDuelOutcome:
    """Everything the agent loop needs to narrate + settle an auto-duel."""
    result: DuelResult           # full engine result (log, stake, powers)
    you_won: bool
    winner: str
    loser: str
    stake: int                   # handshakes transferred (already applied)
    loot: object = None          # equipment.Item you seized (win), or None
    forfeit: object = None       # equipment.Item you lost (loss), or None
    summary: str = ""            # one-line narratable outcome


def auto_resolve(player, peer_stats: dict, inv=None, element: str | None = None,
                 cfg=None, rng=random) -> AutoDuelOutcome:
    """AUTO-resolve a duel against a detected peer and settle everything.

    The loop-callable seam: give it the live PetState, the peer record dict
    (``{"name", "addr", "level", "handshakes", "gear_power", "element"}``),
    the equipment Inventory and (optionally) an element override, and it:

    1. builds both fighters (gear = ``pvp_power()`` incl. set bonuses; stats =
       ``stat_totals()``; your element honoured, never hardcoded Aether),
    2. runs the full turn engine (:func:`_run_duel` via :func:`duel`) with
       :func:`moves.pick_move` acting as the move policy for BOTH sides,
    3. settles the handshake stake on ``player`` and drains it from
       ``peer_stats`` (so a cached sighting can't be farmed), increments
       ``player.duel_wins`` on a win,
    4. rolls gear loot on a win (added to ``inv``) or picks a forfeit on a
       loss (removed from ``inv``).

    Pure-ish: mutates only ``player``, ``peer_stats`` and ``inv``. Never
    raises (the engine degrades to a power tiebreak internally). Callers own
    persistence (gs.save()) and any quest/reward hooks.
    """
    you = fighter_from_pet(player, inv, element)
    them = fighter_from_peer(peer_stats)
    res = duel(you, them, cfg, rng)
    apply_result(player, res)

    loot = forfeit = None
    if res.you_won:
        player.duel_wins = getattr(player, "duel_wins", 0) + 1
        if res.stake:
            peer_stats["handshakes"] = max(
                0, int(peer_stats.get("handshakes", 0) or 0) - res.stake)
        if inv is not None:
            from . import equipment as equip_mod
            loot = equip_mod.roll_item(rng, boost=them.level)
            inv.add(loot)
    elif inv is not None:
        forfeit = inv.pick_forfeit(rng)
        if forfeit is not None:
            inv.remove(forfeit.id)

    bits = [f"{res.winner} beat {res.loser}"]
    if res.stake:
        bits.append(f"seized {res.stake} handshake(s)")
    if loot is not None:
        bits.append(f"looted {loot.name} (+{loot.power} pow)")
    if forfeit is not None:
        bits.append(f"{them.name} stripped your {forfeit.name}")
    summary = ("WON: " if res.you_won else "LOST: ") + ", ".join(bits) + "."

    return AutoDuelOutcome(
        result=res, you_won=res.you_won, winner=res.winner, loser=res.loser,
        stake=res.stake, loot=loot, forfeit=forfeit, summary=summary,
    )
