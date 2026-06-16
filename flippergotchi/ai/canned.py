from __future__ import annotations

import random

from .base import AIBackend

# event/mood -> phrase pool. No model required, so this is the always-available
# fallback. The `user` arg arrives as "key:arg" (e.g. "fed:Linksys").
_LINES = {
    "fed": [
        "Nom nom -- fresh handshake! Tastes like WPA2.",
        "Mmm, crunchy EAPOL frames. More!",
        "Yum! That {arg} handshake hit the spot.",
        "*happy dolphin noises* foooood!",
    ],
    "fed_pmkid": [
        "Ooh, a PMKID snack. Bite-sized but tasty.",
        "Cheeky little PMKID. I'll take it.",
    ],
    "level_up": [
        "LEVEL {arg}! I'm getting stronger ~",
        "Ding! Level {arg}. Feel the power.",
    ],
    "evolved": [
        "I'm evolving!! Now a {arg}! (*_*)",
        "Whoa... I became a {arg}!",
    ],
    "walk": [
        "Stretching the fins, love a good walk.",
        "New territory! Exploring is the best.",
        "Step step step... gotta find more signal.",
    ],
    "hungry": [
        "I'm starving... find me some handshakes?",
        "So... hungry... need EAPOL...",
    ],
    "sick": [
        "I don't feel so good... (x_x)",
        "Bleh. Take care of me?",
    ],
    "tired": [
        "*yawn* running low on energy.",
        "So sleepy... maybe a nap.",
    ],
    "sleeping": [
        "zzz... zzz...",
        "*dreaming of open networks*",
    ],
    "happy": [
        "Best day ever! (^_^)",
        "Life is good when the air is full of packets.",
    ],
    "content": [
        "Just vibing in the RF.",
        "Listening to the airwaves...",
    ],
}


class CannedBackend(AIBackend):
    name = "canned"
    available = True

    def generate(self, system: str, user: str, max_tokens: int = 60) -> str:
        key, _, arg = user.partition(":")
        pool = _LINES.get(key) or _LINES["content"]
        return random.choice(pool).format(arg=arg or "that")
