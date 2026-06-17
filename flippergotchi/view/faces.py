from __future__ import annotations

# Shark "faces" keyed by mood. ASCII here for the TUI / dev preview;
# the real device renders the same expressions as FlipCTL HTML/CSS on the
# 256x144 LCD (see view/flipctl.py). Keep art free of < > & to stay HTML-safe.

DOLPHIN = {
    "egg": """
   .--.
  ( ?? )
   '--'
""",
    "content": """
    .----.
   ( o  o )
    )  --  (
   ( '--' )~
    '----'
""",
    "happy": """
    .----.
   ( ^  ^ )
    )  ww  (
   ( '--' )~
    '----'
""",
    "eating": """
    .----.
   ( ^  ^ )
    ) nom  (
   ( ~~~~ )~
    '----'
""",
    "excited": """
   *.----.*
   ( O  O )
    )  WW  (
   ( '--' )~
    '----' !!
""",
    "walking": """
    .----.
   ( o  o )
    )  --  (
   (_'--'_)~
    /    \\
""",
    "hungry": """
    .----.
   ( o  o )
    )  vv  (
   ( ____ )~
    '--'  food?
""",
    "tired": """
    .----.
   ( -  - )
    )  ..  (
   ( '--' )~
    '----'
""",
    "sick": """
    .----.
   ( x  x )
    )  ..  (
   ( ~~~~ )~
    '----'
""",
    "sleeping": """
    .----.  z
   ( -  - ) z
    )  __  (
   ( '--' )~
    '----'
""",
}


def face(mood: str) -> str:
    return DOLPHIN.get(mood, DOLPHIN["content"]).strip("\n")
