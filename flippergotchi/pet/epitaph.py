"""A tiny, pure helper for the hardcore death summary.

The integrator renders this text on death (before ``reborn``); keeping it here
means the gravestone copy lives outside ``view/*`` and does no I/O. Everything
is read defensively via getattr so it can never raise on a partial/old state.
"""
from __future__ import annotations


def _format_age(seconds) -> str:
    """Human-friendly age from a raw second count (never negative)."""
    try:
        seconds = max(0, int(seconds))
    except (TypeError, ValueError):
        seconds = 0
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    mins = rem // 60
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {mins}m"
    return f"{mins}m"


def epitaph(state, *, lifetime_catches=None) -> str:
    """Format a death summary for a (hardcore) pet: name, age, stage/level and
    lifetime catches. Pure and total -- returns a multi-line string, never raises.

    ``lifetime_catches`` overrides the count; when None it is derived from the
    state's handshake + PMKID counters.
    """
    name = getattr(state, "name", None) or "Flippy"
    level = getattr(state, "level", 1)
    stage = getattr(state, "stage", None) or "egg"

    if lifetime_catches is None:
        catches = int(getattr(state, "handshakes", 0) or 0) + \
            int(getattr(state, "pmkids", 0) or 0)
    else:
        try:
            catches = int(lifetime_catches)
        except (TypeError, ValueError):
            catches = 0

    age_fn = getattr(state, "age_seconds", None)
    age = _format_age(age_fn() if callable(age_fn) else 0)

    return "\n".join([
        "HERE LIES",
        str(name),
        f"the {stage}  ~  Lv {level}",
        f"lived {age}",
        f"caught {catches} monster{'' if catches == 1 else 's'}",
        "R.I.P.",
    ])
