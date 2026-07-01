"""Pure render helpers extracted from ``commands.py``.

These build the display strings / sprite stems and drive the visual ``view/*``
renderers, but they never ``print`` — each returns the rendered value (a string,
a list of frame paths, or a list of text lines) so the command layer stays a thin
"compute data -> hand to view -> print" shell.

Nothing here owns terminal output: callers decide when/what to print.
"""
from __future__ import annotations

import os

from ..game.monsters import label
from . import battle_menu


def player_stem(cfg) -> str:
    """The player shark sprite stem for the configured character variant.

    ``classic`` (or unset) is the bare ``adult`` sprite; any other variant is
    prefixed, e.g. ``neon-adult``. Callers use the returned string as a sprite
    stem; nothing is printed."""
    variant = getattr(cfg, "character_variant", "classic")
    return "adult" if variant in ("classic", "") else f"{variant}-adult"


def render_capture(cfg, m, caught: bool) -> list | None:
    """Best-effort visual net-gun capture frames; never breaks the flow.

    The status HUD reflects the live deauth/capture settings (cfg.deauth_count,
    cfg.capture_timeout) -- the same values the real capture uses. Returns the
    list of frame paths (or ``None`` if rendering was skipped); the caller uses
    the return value to build its own status line -- this function prints nothing."""
    try:
        from . import capture_screen
        out = getattr(cfg, "capture_frames_dir", "/tmp/flippergotchi/capture")
        return capture_screen.render_sequence(
            os.path.expanduser(out),
            {"species": m.species, "name": label(m)},
            caught=caught, player=player_stem(cfg),
            timeout=int(getattr(cfg, "capture_timeout", 20) or 20),
            deauth=int(getattr(cfg, "deauth_count", 5) or 5))
    except Exception:  # noqa: BLE001
        return None


def render_encounter(cfg, m, line: str = "") -> str | None:
    """Best-effort visual encounter card; never breaks the encounter flow.

    Returns the written HTML path (or ``None`` if rendering was skipped); the
    caller uses the return value to build its own status line -- prints nothing."""
    try:
        from . import encounter_screen
        out = getattr(cfg, "encounter_html_out", "/tmp/flippergotchi/encounter.html")
        return encounter_screen.render(os.path.expanduser(out), {
            "species": m.species, "name": label(m), "level": m.level,
            "encryption": m.encryption, "defense": m.defense, "kind": m.kind,
            "shiny": getattr(m, "shiny", False),
        }, line)
    except Exception:  # noqa: BLE001
        return None


# opponent shark species for the duel render (distinct silhouettes that read on
# the mono screen). Picked deterministically per peer so a given rival always
# shows as the same beast -- and never the player's own default sharkface.
_OPP_SPECIES = ("hammerhead", "goblin", "sawshark", "whaleshark")


def opponent_sprite(key: str) -> str:
    """Deterministic opponent shark sprite stem for a duel peer.

    Same ``key`` (peer addr/name) always maps to the same silhouette. Pure;
    returns the stem string."""
    idx = sum(ord(c) for c in (key or "x")) % len(_OPP_SPECIES)
    return f"{_OPP_SPECIES[idx]}-adult"


def dojo_lines(items: list, ready: int, cracked: int, buttons: dict | None = None) -> list:
    """The Battle Dojo terminal text block, as a list of ready-to-print lines.

    ``items`` are the target dicts (name/level/encryption/rarity/kind) the caller
    already built from the ready pool; ``ready`` is that pool's size and
    ``cracked`` the lifetime cracked count. ``buttons`` defaults to
    ``battle_menu.BUTTONS`` (the device D-pad map).

    Returns the lines EXACTLY as ``commands._render_dojo`` would print them
    (leading ``\\n`` on section headers preserved). The caller must
    ``print`` each line -- and it still owns the ``[screen] ...`` render output,
    which this pure helper does not produce."""
    b = buttons if buttons is not None else battle_menu.BUTTONS
    lines = [
        f"\n  == BATTLE DOJO ==   {ready} ready · {cracked} cracked",
        "  [A] AUTO BATTLE  — crack every fresh target  (`battle --all`)",
        "  [B] MANUAL       — pick one below            (`battle <name>`)",
    ]
    if items:
        lines.append("\n  targets you haven't battled yet:")
        for it in items[:12]:
            tag = (it["rarity"] or it["encryption"] or "").upper()
            lines.append(f"    · {it['name']:<22} Lv{it['level']:<3} {tag}")
        if len(items) > 12:
            lines.append(f"    … +{len(items) - 12} more")
    else:
        lines.append("\n  No fresh targets — go catch some monsters first!")
    lines.append(f"\n  device: {b['open']} opens · {b['up']}/{b['down']} move · "
                 f"{b['select']} select · {b['back']} exit")
    return lines
