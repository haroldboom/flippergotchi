from __future__ import annotations

from .state import PetState

# Evolution ladder: (min_level, stage_name). Higher level => later stage.
# `adult` and `prime` fill the old L8->L25 dead zone so an evolution lands roughly
# weekly through month 1 (paired with the gentler cfg.level_exp curve).
#   adult (L14): REAL art already ships (adult.png + <variant>-adult.png).
#   prime (L20): FINAL-ART TODO -- no sprite yet; view/flipctl.py maps it onto the
#                nearest existing stage sprite (alpha) as a placeholder so nothing
#                breaks. Paint dedicated `prime` / `<variant>-prime` sprites later.
STAGES = [
    (1, "egg"),
    (2, "hatchling"),
    (8, "juvenile"),
    (14, "adult"),
    (20, "prime"),
    (25, "alpha"),
    (40, "legend"),
]

# --- post-L40 paragon (non-destructive prestige) ---------------------------
# Levelling never stops and is never reset. Past level `paragon_start_level`,
# each `paragon_every` levels banks one paragon marker on `state.paragon`
# (read/incremented via getattr; the serialised field is added by another agent).
PARAGON_START_LEVEL = 40
PARAGON_EVERY = 10

# --- soft stakes: non-lethal sickness (NORMAL mode) ------------------------
# Module defaults mirror config.py; cfg overrides win (getattr with these).
SICK_HUNGER_THRESHOLD = 85.0
SICK_ONSET_HOURS = 6.0
SICK_RECOVER_HUNGER = 45.0
SICK_HAPPINESS_CAP = 20.0


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


# --- paragon (post-L40 prestige) -------------------------------------------
def paragon_for_level(level: int, cfg=None) -> int:
    """How many paragon markers a pet at ``level`` is entitled to (0 below the
    start level). Pure function -- no state mutation, no level reset."""
    start = int(getattr(cfg, "paragon_start_level", PARAGON_START_LEVEL))
    every = int(getattr(cfg, "paragon_every", PARAGON_EVERY))
    if every <= 0:
        every = PARAGON_EVERY
    return max(0, (int(level) - start) // every)


def paragon_tier(state: PetState, cfg=None) -> int:
    """The pet's current paragon marker count (``state.paragon``, default 0).
    Titles / HUD can read this to render a prestige badge past L40."""
    return int(getattr(state, "paragon", 0) or 0)


def update_paragon(state: PetState, cfg=None) -> int:
    """Non-destructively sync ``state.paragon`` up to what the level entitles it
    to. NEVER resets or lowers level (or the marker). Returns the new tier.

    Called from the XP path on every level-up; also safe to call standalone."""
    want = paragon_for_level(state.level, cfg)
    if want > paragon_tier(state, cfg):
        state.paragon = want
    return paragon_tier(state, cfg)


# --- soft-stakes sickness helpers ------------------------------------------
def _sick_cfg(cfg, name: str, default: float) -> float:
    try:
        return float(getattr(cfg, name, default))
    except (TypeError, ValueError):
        return default


def is_sick(state: PetState) -> bool:
    """NORMAL-mode soft stakes: True once sustained neglect has made the pet sick
    (sulking). While sick the pet stalls XP, refuses to forage and its happiness
    is capped -- but health is NEVER touched, so a normal-mode pet cannot die.

    Always False in hardcore (that mode keeps its unchanged starvation-death
    model instead). Reads the non-persisted ``_sick`` flag set by ``tick``."""
    if bool(getattr(state, "hardcore", False)):
        return False
    return bool(getattr(state, "_sick", False))


def can_forage(state: PetState) -> bool:
    """Forage eligibility: a sick pet won't forage. The integrator should gate
    forage attempts on this (``if mechanics.can_forage(state): ...``)."""
    return not is_sick(state)


def _maybe_recover_sick(state: PetState, cfg) -> bool:
    """Feeding/care recovers sickness once hunger is back at/under the recover
    line. Returns True if the pet just recovered."""
    if not bool(getattr(state, "_sick", False)):
        return False
    rec = _sick_cfg(cfg, "sick_recover_hunger", SICK_RECOVER_HUNGER)
    if state.hunger <= rec:
        state._sick = False
        state._neglect_h = 0.0
        return True
    return False


def _update_sickness(state: PetState, cfg, hours: float) -> None:
    """Advance the neglect->sick->recover state machine. NORMAL mode only; in
    hardcore this is a no-op (sickness disabled, flags cleared)."""
    if bool(getattr(state, "hardcore", False)):
        state._sick = False
        state._neglect_h = 0.0
        return
    onset = _sick_cfg(cfg, "sick_onset_hours", SICK_ONSET_HOURS)
    thr = _sick_cfg(cfg, "sick_hunger_threshold", SICK_HUNGER_THRESHOLD)
    rec = _sick_cfg(cfg, "sick_recover_hunger", SICK_RECOVER_HUNGER)
    cap = _sick_cfg(cfg, "sick_happiness_cap", SICK_HAPPINESS_CAP)
    neglect = float(getattr(state, "_neglect_h", 0.0))
    if state.hunger >= thr:
        neglect += hours                     # neglect accrues while starving
    elif state.hunger <= rec:
        neglect = 0.0                        # genuinely cared for -> debt cleared
    else:
        neglect = max(0.0, neglect - hours)  # in between: slowly recovers
    state._neglect_h = neglect
    if getattr(state, "_sick", False):
        if state.hunger <= rec:              # recover only when properly fed
            state._sick = False
            state._neglect_h = 0.0
    elif neglect >= onset:
        state._sick = True
    if getattr(state, "_sick", False):
        state.happiness = clamp(min(state.happiness, cap))


# --- satiety (well-fed buff) + starvation tuning ---------------------------
SATIETY_PER_RESTORE = 0.8       # satiety gained per hunger-point a food restores
SATIETY_DECAY_PER_HOUR = 12.0   # how fast the well-fed buff fades
# health drain/hour by starvation severity (derived from hunger, no new field).
# NORMAL mode floors health at 1 (faint); HARDCORE lets it reach 0 (-> death).
# The faint drain is deliberately gentler than the "starving" ramp so the final
# slide to 0 HP is a visible slope, not a cliff -- this widens the death runway.
_STARVE_DRAIN = {"": 0.0, "peckish": 0.0, "hungry": 6.0, "starving": 14.0, "faint": 18.0}

# --- hardcore death runway --------------------------------------------------
# Once a hardcore pet bottoms out at 0 HP it does NOT die instantly. It must
# spend this many *real* ticks in the faint stage first (a fixed count, so the
# grace is independent of time_scale -- a demo cranking time_scale still gets
# the same number of "ABOUT TO DIE" frames to react on). The counter lives on
# the state instance as a non-persisted attribute (`_faint_ticks`) so no new
# serialised field is added.
FAINT_DEATH_GRACE_TICKS = 3

# --- sleep / energy restore -------------------------------------------------
# maybe_sleep() puts a tired pet to sleep at/under the low threshold and wakes
# it once rested at/over the high threshold. tick() already restores energy
# while asleep, so this closes the loop: energy is no longer a one-way drain.
SLEEP_ENERGY_LOW = 20.0    # fall asleep at/under this energy
WAKE_ENERGY_HIGH = 80.0    # wake back up at/over this energy


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

    Death is NOT instant: even at 0 HP the pet survives until it has spent
    ``FAINT_DEATH_GRACE_TICKS`` real ticks in the faint stage (see ``tick``),
    giving the player a fixed, time_scale-independent runway of warning frames.
    In Normal mode this is always False (health is floored at 1)."""
    if not bool(getattr(state, "hardcore", False)) or state.health > 0:
        return False
    return getattr(state, "_faint_ticks", 0) >= FAINT_DEATH_GRACE_TICKS


def reborn(state: PetState) -> PetState:
    """A fresh egg after a hardcore death -- keeps only the name, element and the
    locked-in hardcore mode; all progress/stats reset."""
    return PetState(name=state.name, element=getattr(state, "element", "Aether"),
                    hardcore=getattr(state, "hardcore", False))


def maybe_sleep(state: PetState, cfg) -> bool:
    """Manage the sleep/wake cycle from energy; call once per tick.

    A tired, awake pet falls asleep at/under the low-energy threshold; a rested,
    sleeping pet wakes at/over the high threshold. While asleep, ``tick`` restores
    energy (and slows hunger), so this is the restore path that makes the
    tired/sleeping faces reachable. Returns the resulting ``asleep`` flag.

    Thresholds come from ``cfg`` (``sleep_energy_low`` / ``wake_energy_high``) via
    getattr with module-constant defaults; a malformed cfg where low >= high is
    clamped so the pet still eventually wakes."""
    low = getattr(cfg, "sleep_energy_low", SLEEP_ENERGY_LOW)
    high = getattr(cfg, "wake_energy_high", WAKE_ENERGY_HIGH)
    try:
        low = float(low)
        high = float(high)
    except (TypeError, ValueError):
        low, high = SLEEP_ENERGY_LOW, WAKE_ENERGY_HIGH
    if high <= low:                       # guard against a broken cfg
        high = low + 1.0
    if state.asleep:
        if state.energy >= high:
            state.asleep = False
    elif state.energy <= low:
        state.asleep = True
    return state.asleep


def mood(state: PetState) -> str:
    if state.asleep:
        return "sleeping"
    if is_sick(state):
        return "sick"
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

    # hardcore death runway: count consecutive faint-stage ticks so is_dead can
    # hold off until the grace window elapses. Any recovery out of faint resets
    # the countdown (a fed-then-neglected pet gets the full runway again).
    if getattr(state, "hardcore", False) and starvation_stage(state) == "faint":
        state._faint_ticks = getattr(state, "_faint_ticks", 0) + 1
    else:
        state._faint_ticks = 0

    # soft stakes: advance the non-lethal sickness state machine (normal mode)
    _update_sickness(state, cfg, hours)

    state.stage = stage_for_level(state.level)


def grant_xp(state: PetState, amount: float, cfg) -> list:
    """Public XP grant (e.g. quest rewards). Returns level-up events."""
    return _gain_xp(state, amount, cfg)


def _gain_xp(state: PetState, amount: float, cfg) -> list:
    """Add xp, rolling over level-ups. Returns a list of progress events.

    Soft stakes: a sick pet stalls -- it earns NO xp until cared for (this gates
    every xp source: walk/collect/snack/quest rewards flow through here)."""
    if is_sick(state):
        return []
    events = []
    before_paragon = paragon_tier(state, cfg)
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
    # non-destructive prestige: bank paragon markers gained past L40 (no reset)
    after_paragon = update_paragon(state, cfg)
    if after_paragon > before_paragon:
        events.append({"type": "paragon", "tier": after_paragon})
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
    # feeding is care: it can lift sickness (before the xp grant, so the recovering
    # meal itself resumes earning xp)
    _maybe_recover_sick(state, cfg)
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
