from __future__ import annotations

import random

from .base import AIBackend

# event/mood -> phrase pool. No model required, so this is the always-available
# fallback. The `user` arg arrives as "key:arg" (e.g. "fed:Linksys").
_LINES = {
    "caught": [
        "Gotcha! {arg} is in the bestiary now!",
        "Caught {arg}! Another one for the collection.",
        "Net's full -- {arg} captured! (^o^)",
        "*triumphant shark noises* got {arg}!",
    ],
    "fed": [
        "Nom nom -- tasty little snack!",
        "Mmm, found a treat on the walk. More!",
        "Yum! That snack hit the spot.",
        "*happy shark noises* foooood!",
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
        "I'm starving... let's walk and forage a snack?",
        "So... hungry... need a treat...",
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
