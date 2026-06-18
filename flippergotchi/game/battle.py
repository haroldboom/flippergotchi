"""Battling a captured monster = trying to crack its handshake.

Flow:  validate capture  ->  local hashcat + wordlists  ->  (if it fails &
you allow it)  cloud crack.

Authorization is CONSENT-BASED, not a network allow-list: the player agrees once
to the on-screen WARNING (the `battle` command / on-the-fly crack consent) and
that standing consent authorizes cracking -- you never edit a config file to
play. ``is_authorized`` below remains only as an OPTIONAL convenience scope (does
the target match cfg.home_networks?) used by the standalone capture/cloud
commands; ``battle()`` itself does NOT refuse on it. Collecting/scanning monsters
is always fine; the crack is gated by consent, captured at the call site.

The actual crack pipeline lives in ``game/cracking.py`` (validate -> convert ->
hashcat -> parse, with a no-hardware simulator). This module owns the
authorization gate and the game wiring, and returns the legacy result dict
{"result","via","key", ...} so existing callers/tests keep working.
"""
from __future__ import annotations

from .analysis import assess
from .cracking import CloudCracker, CrackResult, LocalCracker

__all__ = ["is_authorized", "battle", "LocalCracker", "CloudCracker", "CrackResult"]


def is_authorized(monster, cfg) -> bool:
    """OPTIONAL convenience scope check: does the monster match cfg.home_networks?

    NOT a hard gate on battling -- the game's authorization is the on-screen
    consent the player agrees to. Kept for the standalone capture/cloud commands
    and API back-compat; ``battle()`` does not call it to refuse.
    """
    home = getattr(cfg, "home_networks", []) or []
    if isinstance(home, str):          # defensive: never iterate a string's chars
        home = [home]
    needles = [str(n).lower() for n in home if n]
    hay = f"{monster.name} {monster.id}".lower()
    return any(n in hay for n in needles)


def battle(monster, cfg, handshake_path: str | None = None,
           force_authorized: bool = False) -> dict:
    # Authorization is the player's responsibility, captured by the on-screen
    # WARNING they agree to (the `battle` command / on-the-fly consent) -- not a
    # network allow-list. ``force_authorized`` is kept for API back-compat.
    if monster.kind == "ble":
        # BLE battling: crack the pairing (crackle) or take control (GATT write).
        from .blebattle import battle_ble
        return battle_ble(monster, cfg)

    res: CrackResult = LocalCracker(cfg).crack(monster, handshake_path)
    if res.result == "failed" and assess(monster.__dict__).recommend_cloud \
            and getattr(cfg, "cloud_enabled", False):
        res = CloudCracker(cfg).submit(monster, handshake_path)

    if res.result == "cracked":
        monster.defeated = True
        monster.key = res.key
    return res.to_dict()
