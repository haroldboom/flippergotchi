from __future__ import annotations

from .state import PetState

# Evolution ladder: (min_level, stage_name). Higher level => later stage.
STAGES = [
    (1, "egg"),
    (2, "hatchling"),
    (4, "fingerling"),
    (8, "juvenile"),
    (15, "adult"),
    (25, "alpha"),
    (40, "legend"),
]


def clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def xp_to_next(level: int, cfg) -> float:
    return cfg.base_xp * (level ** cfg.level_exp)


def stage_for_level(level: int) -> str:
    name = STAGES[0][1]
    for lvl, s in STAGES:
        if level >= lvl:
            name = s
    return name


def mood(state: PetState) -> str:
    if state.asleep:
        return "sleeping"
    if state.health < 30:
        return "sick"
    if state.hunger > 75:
        return "hungry"
    if state.energy < 20:
        return "tired"
    if state.happiness > 75:
        return "happy"
    return "content"


def tick(state: PetState, dt: float, cfg) -> None:
    """Apply time-based decay for `dt` seconds (already time-scaled)."""
    if dt <= 0:
        return
    hours = dt / 3600.0
    if state.asleep:
        state.energy = clamp(state.energy + cfg.energy_per_hour * hours * 2.0)
        state.hunger = clamp(state.hunger + cfg.hunger_per_hour * hours * 0.4)
    else:
        state.hunger = clamp(state.hunger + cfg.hunger_per_hour * hours)
        state.energy = clamp(state.energy - cfg.energy_per_hour * hours)

    # health rewards care, punishes neglect
    if state.hunger > 80 or state.energy < 10:
        state.health = clamp(state.health - 10.0 * hours)
    elif state.hunger < 40 and state.energy > 40:
        state.health = clamp(state.health + 5.0 * hours)

    # happiness drifts toward a hunger-driven baseline
    target = clamp(90 - state.hunger)
    state.happiness = clamp(state.happiness + (target - state.happiness) * min(1.0, hours))

    state.stage = stage_for_level(state.level)


def _gain_xp(state: PetState, amount: float, cfg) -> list:
    """Add xp, rolling over level-ups. Returns a list of progress events."""
    events = []
    state.xp += amount
    while state.xp >= xp_to_next(state.level, cfg):
        state.xp -= xp_to_next(state.level, cfg)
        state.level += 1
        evt = {"type": "level_up", "level": state.level}
        new_stage = stage_for_level(state.level)
        if new_stage != state.stage:
            state.stage = new_stage
            evt["evolved_to"] = new_stage
        events.append(evt)
    return events


def collect(state: PetState, kind: str, cfg) -> list:
    """Capture a handshake/PMKID = CATCH a monster. Adds it to your handshake
    pool (duel stakes) and grants XP. APs are monsters, NOT food, so this does
    not touch hunger."""
    if kind == "pmkid":
        state.pmkids += 1
        xp = cfg.xp_per_pmkid
    else:
        state.handshakes += 1
        xp = cfg.xp_per_handshake
    state.happiness = clamp(state.happiness + 5)
    return [{"type": "caught", "kind": kind}] + _gain_xp(state, xp, cfg)


def snack(state: PetState, cfg) -> list:
    """Eat a foraged snack (found while walking). This is the pet's FOOD: it
    lowers hunger. No handshake counters change."""
    state.hunger = clamp(state.hunger - cfg.forage_food)
    state.happiness = clamp(state.happiness + 3)
    return [{"type": "fed", "kind": "snack"}] + _gain_xp(state, cfg.xp_per_snack, cfg)


def walk(state: PetState, meters: float, cfg) -> list:
    """GPS movement is exercise: xp + a little hunger/energy cost."""
    if meters <= 0:
        return []
    state.distance_m += meters
    state.energy = clamp(state.energy - meters * cfg.energy_per_meter)
    state.hunger = clamp(state.hunger + meters * 0.002)
    state.happiness = clamp(state.happiness + min(4.0, meters * 0.01))
    return _gain_xp(state, meters * cfg.xp_per_meter, cfg)
