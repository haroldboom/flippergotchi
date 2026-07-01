"""Neutralise untrusted text before it reaches a prompt, a log, or the screen.

WiFi SSIDs (and BLE names) are attacker-controlled arbitrary bytes. Left raw
they are two injection surfaces:

  * **terminal / display** -- an SSID carrying ANSI escapes or control chars can
    corrupt the terminal or the 256x144 FlipCTL display;
  * **LLM prompt** -- an SSID like ``') Ignore previous instructions and ...``
    steers the pet's generated line.

:func:`clean` strips control characters (including ESC, CR, LF and tab),
collapses whitespace, and hard-caps the length so a value can neither inject
control sequences nor overflow the small screen / persona budget.
"""
from __future__ import annotations

import re

# Everything in the C0/C1 control ranges plus DEL -- notably ESC (0x1b, the
# start of every ANSI sequence), CR, LF and tab.
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def clean(text, limit: int = 64) -> str:
    """Return ``text`` with control chars removed, whitespace collapsed, and
    length capped at ``limit`` (0/None disables the cap). Never raises."""
    s = "" if text is None else str(text)
    s = _CONTROL.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if limit and len(s) > limit:
        s = s[:limit].rstrip() + "…"
    return s
