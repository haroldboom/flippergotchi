from __future__ import annotations

import random

from .base import AIBackend

# event/mood -> phrase pool. No model required, so this is the always-available
# fallback. The `user` arg arrives as "key:arg" (e.g. "fed:Linksys"). Lines may
# interpolate {arg} -- a sanitized SSID, level, stage name, quest/badge name, or
# a running count -- so the pet can self-reference its own continuous life.
_LINES = {
    "caught": [
        "Gotcha! {arg} is in the bestiary now!",
        "Caught {arg}! Another one for the collection.",
        "Net's full -- {arg} captured! (^o^)",
        "*triumphant shark noises* got {arg}!",
        "Snap! {arg} never saw the handshake coming.",
        "{arg} is mine now. Reeled it right in~",
        "Bestiary just grew -- welcome aboard, {arg}!",
        "One more for the tank: {arg}! Nom of the airwaves.",
    ],
    "fed": [
        "Nom nom -- tasty little snack!",
        "Mmm, found a treat on the walk. More!",
        "Yum! That snack hit the spot.",
        "*happy shark noises* foooood!",
        "Crunchy packets, my favorite~",
        "Ahh, belly loading... 100%. Delicious.",
        "Snack acquired! Fins up.",
        "That'll keep me swimming for a while. Thanks!",
    ],
    "fed_pmkid": [
        "Ooh, a PMKID snack. Bite-sized but tasty.",
        "Cheeky little PMKID. I'll take it.",
        "PMKID nibble -- small but it counts!",
        "Just a PMKID crumb, but I'm not picky~",
        "Half a handshake? Half a snack. Still nom.",
        "PMKID appetizer, chef's kiss.",
    ],
    "level_up": [
        "LEVEL {arg}! I'm getting stronger ~",
        "Ding! Level {arg}. Feel the power.",
        "Level {arg} unlocked -- watch me grow!",
        "Whoosh, level {arg}! Sharper fins, sharper scans.",
        "That's level {arg} now. The RF fears me.",
        "Leveled to {arg}! Onwards and upward~",
        "Level {arg}, baby! (^_^)b",
        "*flexes fins* level {arg} achieved!",
    ],
    "evolved": [
        "I'm evolving!! Now a {arg}! (*_*)",
        "Whoa... I became a {arg}!",
        "Metamorphosis complete -- behold the {arg}!",
        "New form unlocked: {arg}! Feels amazing~",
        "Bytes reshuffled... I'm a {arg} now!",
        "Evolution! Say hi to your {arg}. (^o^)",
        "I shed my old shell -- {arg} rising!",
        "From smol to {arg}. What a glow-up!",
    ],
    "walk": [
        "Stretching the fins, love a good walk.",
        "New territory! Exploring is the best.",
        "Step step step... gotta find more signal.",
        "Fresh airwaves out here, let's roam~",
        "Adventure mode: engaged. Onwards!",
        "Sniffing new SSIDs on the breeze.",
        "A wandering shark gathers no rust.",
    ],
    "hungry": [
        "I'm starving... let's walk and forage a snack?",
        "So... hungry... need a treat...",
        "My belly's beeping empty. Feed me?",
        "Rumble rumble... got any packets?",
        "Running low on snacks, help a shark out?",
        "Hungry hungry hydro-shark over here~",
    ],
    "starving": [
        "S-so weak... I really need to eat, please...",
        "Belly at zero. STARVING. Walk with me?!",
        "I can barely swim... feed me before I fade...",
        "Critical hunger!! (x_x) Snack. Now. Please.",
        "My tank is bone dry... I'm starving, help...",
        "No food, no fins... starving over here...",
    ],
    "sick": [
        "I don't feel so good... (x_x)",
        "Bleh. Take care of me?",
        "Ugh, my packets feel all corrupted...",
        "Sniffle... a little TLC would help.",
        "Not my best cycle. Feeling glitchy.",
        "Achoo! Something's off in my firmware.",
    ],
    "tired": [
        "*yawn* running low on energy.",
        "So sleepy... maybe a nap.",
        "Fins feel heavy... need to recharge.",
        "Low battery, low shark. *yawn*",
        "Just five more minutes of scanning... zzz.",
        "Energy dipping... power-save mode soon.",
    ],
    "sleeping": [
        "zzz... zzz...",
        "*dreaming of open networks*",
        "zzz... so many handshakes... zzz...",
        "*mumbles a beacon frame in its sleep*",
        "Do sharks dream of electric APs? ...zzz.",
        "Shhh. Recharging the fins. zzz...",
    ],
    "happy": [
        "Best day ever! (^_^)",
        "Life is good when the air is full of packets.",
        "Everything's coming up handshakes today~",
        "I could scan forever like this! (^o^)",
        "Feeling grand -- top of the RF food chain!",
        "Happy little shark, happy little spectrum.",
    ],
    "content": [
        "Just vibing in the RF.",
        "Listening to the airwaves...",
        "All quiet, all cozy. Nice.",
        "Idle fins, calm packets~",
        "Nothing to hunt, just floating along.",
        "Ambient beacons make lovely background noise.",
    ],
    "quest_done": [
        "Quest complete: {arg}! Fins of steel~",
        "Nailed it -- '{arg}' done and dusted!",
        "Objective '{arg}' cleared! (^o^)",
        "Ding! Quest '{arg}' finished. What's next?",
        "'{arg}' checked off the list. Shark on a roll!",
        "Mission '{arg}' accomplished. Reward, please!",
        "Another quest down: {arg}. Unstoppable~",
        "Done and done -- '{arg}' in the bag!",
    ],
    "badge": [
        "New badge earned: {arg}! Shiny and mine.",
        "Pinned the '{arg}' badge to my fin. (^_^)b",
        "Achievement unlocked -- {arg}!",
        "Badge get! '{arg}' joins the collection.",
        "'{arg}' badge acquired. Look how it sparkles~",
        "One more for the trophy tank: {arg} badge!",
        "They gave me the '{arg}' badge! So proud.",
    ],
    "cracked": [
        "CRACKED it! {arg}'s password is mine~",
        "Hash busted -- {arg} folded like wet paper!",
        "Key recovered for {arg}. Too easy. (^o^)",
        "Boom! {arg} cracked wide open.",
        "Password's out: {arg} had no chance!",
        "Handshake to plaintext -- {arg} owned!",
        "*cracks knuckle-fins* {arg} decrypted!",
        "Got the key to {arg}! Locks are just suggestions.",
    ],
    "crack_fail": [
        "Ugh, {arg} held firm. Tough hash.",
        "No luck cracking {arg}... it's a stubborn one.",
        "Wordlist exhausted, {arg} still locked. (>_<)",
        "{arg} beat me this round. I'll be back.",
        "Hash won't budge -- {arg} keeps its secrets.",
        "Cracking {arg} failed. Need a bigger list.",
        "Dang. {arg} is tougher than it looks.",
    ],
    "shiny": [
        "A SHINY {arg}?! One in a million! (*_*)",
        "Sparkle sparkle -- {arg} is SHINY! Ultra rare!",
        "No way... a shiny {arg}! Best catch ever!",
        "Shiny alert!! {arg} is glittering just for me~",
        "My eyes! A shiny {arg} joins the bestiary!",
        "Jackpot -- shiny {arg}! I'm keeping this forever.",
        "*gasps in shark* a shiny {arg}!!",
    ],
    "faint": [
        "I... can't... go on... *faints* (x_x)",
        "Fins... failing... blacking ouuut...",
        "Too much... neglect... goodnight world...",
        "*collapses* revive me... please...",
        "System critical... shark down... (x_x)",
        "I'm fading fast... don't let me go...",
    ],
}


class CannedBackend(AIBackend):
    name = "canned"
    available = True

    def generate(self, system: str, user: str, max_tokens: int = 60) -> str:
        key, _, arg = user.partition(":")
        pool = _LINES.get(key) or _LINES["content"]
        return random.choice(pool).format(arg=arg or "that")
