"""Pokemon GO-style WiFi encounters.

Flow:  AP detected -> PROMPT (Capture or Run?) -> player chooses
         capture -> attempt a handshake -> CAUGHT (net animation) or ESCAPED
         run     -> FLED (flee animation), back to walking

NOTE: *capturing* a handshake is an RF act (works on any AP) and is separate
from *battling* (cracking), which is authorization-gated and happens at home.
Capture success depends on radio conditions (clients present, signal), NOT on
encryption strength - you can grab a WPA3 handshake, you just can't crack it.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from .monsters import Monster

# states
PROMPT = "prompt"
CAUGHT = "caught"
ESCAPED = "escaped"
FLED = "fled"


def capture_chance(m: Monster) -> float:
    """Probability of grabbing a handshake this encounter (RF, not crypto)."""
    base = 0.45
    base += 0.10 * min(m.clients, 4)         # clients => deauth -> easy handshake
    base += (m.signal + 90) / 100.0 * 0.35   # stronger signal helps (-40..-90 dBm)
    return max(0.10, min(0.95, base))


@dataclass
class Encounter:
    monster: Monster
    state: str = PROMPT
    animation: str = "appear"
    message: str = ""

    def __post_init__(self):
        self.message = f"A wild {self.monster.species} ({self.monster.name}) appeared!"

    def choose(self, action: str, rng=random) -> "Encounter":
        """action: 'capture' | 'run'. Resolves the encounter (simulated roll)."""
        if action == "run":
            self.state = FLED
            self.animation = "flee"
            self.message = "You quietly slipped away."
            return self
        # capture attempt (sim): roll on RF conditions. On hardware the agent
        # instead runs a real deauth+capture and calls resolve_capture().
        return self.resolve_capture(rng.random() < capture_chance(self.monster))

    def resolve_capture(self, captured: bool, path: str = "") -> "Encounter":
        """Set the outcome from a REAL capture attempt (a hardware backend ran
        the deauth + handshake listen) rather than the simulated roll.

        ``captured`` = a usable handshake/PMKID was obtained; ``path`` is the
        on-disk capture file (kept on the monster for later cracking/upload)."""
        if captured:
            self.monster.captured = True
            if path:
                self.monster.capture_path = path
            self.state = CAUGHT
            self.animation = "catch"
            self.message = f"Gotcha! {self.monster.name}'s handshake was netted!"
        else:
            self.state = ESCAPED
            self.animation = "escape"
            self.message = f"{self.monster.name} got away - no handshake this time."
        return self


def auto_choice(monster: Monster, rng=random) -> str:
    """Headless policy (sim / no UI). On the device this comes from a button."""
    # a keen collector: mostly capture, occasionally flee for flavour
    return "run" if rng.random() < 0.15 else "capture"
