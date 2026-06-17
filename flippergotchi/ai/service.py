from __future__ import annotations

from ..pet import mechanics
from .canned import CannedBackend

PERSONA = (
    "You are {name}, a cyberpunk shark pet living inside a Flipper One. "
    "You scan for nearby WiFi access points and capture the ones you target "
    "(netting an AP's handshake catches it like a monster); walking forages your "
    "food. You do NOT auto-attack everything. "
    "Reply with ONE short, cute, playful sentence (max 14 words). "
    "Mood: {mood}. Level {level}, stage {stage}."
)


def build_backend(cfg):
    """Pick the best available backend, degrading gracefully to canned phrases."""
    backend = (cfg.ai_backend or "canned").lower()
    if backend == "npu":
        try:
            from .rkllm_npu import RkllmBackend
            b = RkllmBackend(cfg)
            if b.available:
                return b
        except Exception as e:
            print(f"[ai] NPU backend unavailable ({e}); falling back")
    elif backend == "cpu":
        try:
            from .cpu_llama import LlamaCppBackend
            b = LlamaCppBackend(cfg)
            if b.available:
                return b
        except Exception as e:
            print(f"[ai] CPU backend unavailable ({e}); falling back to canned")
    return CannedBackend()


class AIService:
    """Turns game events + pet state into a spoken line, via any backend."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.backend = build_backend(cfg)

    def speak(self, event_key: str, state, arg: str = "", sub: str = "") -> str:
        # `arg` is the display flavor (ssid / level / stage); `sub` disambiguates
        # (e.g. handshake vs pmkid). Canned wants a structured "key:arg"; LLM
        # backends want prose.
        if self.backend.name == "canned":
            key = "fed_pmkid" if (event_key == "fed" and sub == "pmkid") else event_key
            return self.backend.generate("", f"{key}:{arg}")
        system = PERSONA.format(name=state.name, mood=mechanics.mood(state),
                                level=state.level, stage=state.stage)
        try:
            return self.backend.generate(system, self._describe(event_key, arg, sub)).strip()
        except Exception:
            return CannedBackend().generate("", f"{event_key}:{arg}")

    def analyze(self, target: dict) -> str:
        """Analyst line for a target AP: difficulty + suggested attack."""
        from ..game.analysis import assess
        a = assess(target)
        if self.backend.name == "canned":
            return f"{a.ssid} [{a.encryption}] -> {a.label} ({a.difficulty}/100). {a.attack}"
        system = ("You are a witty WiFi-pentest coach inside a game. "
                  "Reply in at most 2 short, practical sentences.")
        facts = (f"SSID {a.ssid}, {a.encryption}, difficulty {a.label} "
                 f"{a.difficulty}/100. Notes: {'; '.join(a.reasons) or 'none'}. "
                 f"Plan: {a.attack} Cmd: {a.hashcat_cmd or 'n/a'}.")
        try:
            return self.backend.generate(system, "Coach the player: " + facts).strip()
        except Exception:
            return f"{a.ssid} [{a.encryption}] -> {a.label} ({a.difficulty}/100). {a.attack}"

    @staticmethod
    def _describe(event_key: str, arg: str, sub: str = "") -> str:
        return {
            "caught": f"You just CAUGHT a wild AP-monster ('{arg or 'one'}') in your "
                      "net! React with triumph.",
            "fed": "You ate a tasty snack you foraged while walking. React happily.",
            "level_up": f"You reached level {arg}. Celebrate briefly.",
            "evolved": f"You evolved into a {arg}. React with awe.",
            "walk": "You're out walking and exploring new ground. React.",
            "hungry": "You're very hungry and need to forage a snack. Complain cutely.",
            "sick": "You feel sick from neglect. React sadly.",
            "tired": "You're low on energy. React sleepily.",
            "happy": "You're delighted with life right now. React.",
            "sleeping": "You're napping. Mumble something dreamy.",
            "content": "You're calmly vibing. Say something small.",
        }.get(event_key, "Say something in character.")
