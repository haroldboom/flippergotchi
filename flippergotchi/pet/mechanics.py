from __future__ import annotations

from .state import PetState

# Evolution ladder: (min_level, stage_name). Higher level => later stage.
STAGES = [
    (1, "egg"),
    (2, "hatchling"),
    (8, "juvenile"),
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


# --- satiety (well-fed buff) + starvation tuning ---------------------------
SATIETY_PER_RESTORE = 0.8       # satiety gained per hunger-point a food restores
SATIETY_DECAY_PER_HOUR = 12.0   # how fast the well-fed buff fades
# health drain/hour by starvation severity (derived from hunger, no new field).
# NORMAL mode floors health at 1 (faint); HARDCORE lets it reach 0 (-> death).
_STARVE_DRAIN = {"": 0.0, "peckish": 0.0, "hungry": 6.0, "starving": 14.0, "faint": 24.0}


def starvation_stage(state: PetState) -> str:
    """The escalating hunger stage, derived from `hunger` (no persisted field)."""
    h = state.hunger
    if h >= 100:
        return "faint"
    if h >= 90:
        return "starving"
    if h >= 75:
        return "hungry"
    if h >= 60:
        return "peckish"
    return ""


def is_dead(state: PetState) -> bool:
    """Hardcore ONLY: the pet has starved to death and must be reborn as an egg.
    In Normal mode this is always False (health is floored at 1)."""
    return bool(getattr(state, "hardcore", False)) and state.health <= 0


def reborn(state: PetState) -> PetState:
    """A fresh egg after a hardcore death -- keeps only the name, element and the
    locked-in hardcore mode; all progress/stats reset."""
    return PetState(name=state.name, element=getattr(state, "element", "Aether"),
                    hardcore=getattr(state, "hardcore", False))


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

    # the well-fed buff fades over time
    state.satiety = clamp(state.satiety - SATIETY_DECAY_PER_HOUR * hours)

    # health: starvation drains it (severity-scaled), care heals it. NORMAL mode
    # floors at 1 (faint, recover by feeding); HARDCORE lets it reach 0 -> death.
    drain = _STARVE_DRAIN.get(starvation_stage(state), 0.0)
    if state.energy < 10:
        drain = max(drain, 10.0)
    if drain > 0:
        floor = 0.0 if getattr(state, "hardcore", False) else 1.0
        state.health = clamp(state.health - drain * hours, lo=floor)
    elif state.hunger < 40 and state.energy > 40:
        state.health = clamp(state.health + 5.0 * hours)

    # happiness drifts toward a hunger-driven baseline
    target = clamp(90 - state.hunger)
    state.happiness = clamp(state.happiness + (target - state.happiness) * min(1.0, hours))

    state.stage = stage_for_level(state.level)


def grant_xp(state: PetState, amount: float, cfg) -> list:
    """Public XP grant (e.g. quest rewards). Returns level-up events."""
    return _gain_xp(state, amount, cfg)


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


def snack(state: PetState, cfg, kind=None) -> list:
    """Eat a snack. This is the pet's FOOD: it lowers hunger. No handshake
    counters change. ``kind`` is an optional ``game.food.FoodKind`` whose
    ``restore`` overrides the flat ``cfg.forage_food`` -- with ``kind=None`` the
    behaviour is identical to before, so every existing caller is unchanged."""
    restore = cfg.forage_food if kind is None else getattr(kind, "restore", cfg.forage_food)
    label = "snack" if kind is None else getattr(kind, "id", "snack")
    state.hunger = clamp(state.hunger - restore)
    # eating banks a well-fed buff (bigger meals -> more satiety)
    state.satiety = clamp(state.satiety + restore * SATIETY_PER_RESTORE)
    state.happiness = clamp(state.happiness + 3)
    return [{"type": "fed", "kind": label}] + _gain_xp(state, cfg.xp_per_snack, cfg)


def walk(state: PetState, meters: float, cfg) -> list:
    """GPS movement is exercise: xp + a little hunger/energy cost."""
    if meters <= 0:
        return []
    state.distance_m += meters
    state.energy = clamp(state.energy - meters * cfg.energy_per_meter)
    state.hunger = clamp(state.hunger + meters * 0.002)
    state.happiness = clamp(state.happiness + min(4.0, meters * 0.01))
    return _gain_xp(state, meters * cfg.xp_per_meter, cfg)
