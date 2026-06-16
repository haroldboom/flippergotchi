from __future__ import annotations

import os
from dataclasses import dataclass, field, fields

try:
    import tomllib  # py3.11+
except ModuleNotFoundError:  # pragma: no cover - 3.10 falls back to defaults
    tomllib = None


@dataclass
class Config:
    """All tunables. Loaded from a TOML file (py3.11+) and/or CLI overrides."""

    name: str = "Flippy"
    simulate: bool = False
    tick_interval: float = 1.0     # seconds of wall-clock per tick
    time_scale: float = 1.0        # multiply elapsed time for decay (sim/demo)

    # wifi / bettercap
    interface: str = "mon0"
    bettercap_url: str = "http://127.0.0.1:8081"

    # tamagotchi mechanics
    hunger_per_hour: float = 50.0      # how fast it gets hungry
    energy_per_hour: float = 18.0      # how fast it tires while awake
    food_value_handshake: float = 14.0  # hunger restored by a full handshake
    food_value_pmkid: float = 9.0       # hunger restored by a PMKID snack
    xp_per_handshake: float = 12.0
    xp_per_pmkid: float = 7.0
    xp_per_meter: float = 0.15          # walking = exercise = xp
    energy_per_meter: float = 0.02
    base_xp: float = 120.0              # xp_to_next = base_xp * level**level_exp
    level_exp: float = 1.6

    # ai backend: "canned" (no deps) | "cpu" (llama.cpp) | "npu" (RKLLM, future)
    ai_backend: str = "canned"
    ai_model_path: str = ""

    # gps: "sim" (random wander) | "gpsd" (real device) | "off"
    gps_mode: str = "sim"
    gpsd_host: str = "127.0.0.1"
    gpsd_port: int = 2947

    # --- RPG: monsters, battles, cracking ---
    bestiary_path: str = "~/.flippergotchi/bestiary.json"
    scan_bluetooth: bool = True
    # cracking is ONLY allowed against networks matching these (ssid/bssid
    # substrings) - your own "dojo". Empty => battles are refused by default.
    home_networks: list = field(default_factory=list)
    hashcat_bin: str = "hashcat"
    wordlist: str = "/usr/share/wordlists/rockyou.txt"
    cloud_enabled: bool = False              # allow upload fallback on hard targets
    cloud_service: str = "wpa-sec"           # wpa-sec | onlinehashcrack
    # "home" = where battling is offered: geofence and/or a home network in range
    home_location: list = field(default_factory=list)  # [lat, lon]
    home_radius_m: float = 80.0
    anim_delay: float = 0.18                  # seconds between encounter frames (TUI)
    encounter_cooldown: int = 5               # ticks before re-encountering an AP

    # view / io
    tui: bool = True
    flipctl_html_out: str = "/tmp/flippergotchi/face.html"
    state_path: str = "~/.flippergotchi/state.json"

    @classmethod
    def load(cls, path: str | None) -> "Config":
        cfg = cls()
        if not path:
            return cfg
        p = os.path.expanduser(path)
        if not os.path.exists(p):
            return cfg
        if tomllib is None:
            print("[config] python<3.11 has no tomllib; using defaults + CLI flags")
            return cfg
        with open(p, "rb") as f:
            data = tomllib.load(f)
        names = {fld.name for fld in fields(cls)}
        for k, v in data.items():
            if k in names:
                setattr(cfg, k, v)
        return cfg
