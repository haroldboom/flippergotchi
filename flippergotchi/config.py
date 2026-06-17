from __future__ import annotations

import os
from dataclasses import dataclass, field, fields

try:
    import tomllib  # py3.11+
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None


def _coerce_scalar(v: str):
    v = v.strip()
    if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
        return v[1:-1]
    low = v.lower()
    if low in ("true", "false"):
        return low == "true"
    for cast in (int, float):
        try:
            return cast(v)
        except ValueError:
            pass
    return v


def _coerce(v: str):
    v = v.strip()
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        return [_coerce_scalar(x) for x in inner.split(",") if x.strip()] if inner else []
    return _coerce_scalar(v)


def _strip_comment(val: str) -> str:
    """Drop an inline '#' comment, respecting double-quoted strings."""
    out, inq = [], False
    for ch in val:
        if ch == '"':
            inq = not inq
        elif ch == "#" and not inq:
            break
        out.append(ch)
    return "".join(out)


def _parse_toml_lite(text: str) -> dict:
    """Minimal TOML subset (key = string|number|bool|flat-array) for Python 3.10,
    which lacks tomllib. Good enough for this project's flat config."""
    out = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("["):
            continue
        key, sep, val = line.partition("=")
        if not sep:
            continue
        out[key.strip()] = _coerce(_strip_comment(val))
    return out


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
    bettercap_user: str = "user"       # REST API basic-auth (live mode)
    bettercap_pass: str = "pass"

    # tamagotchi mechanics
    hunger_per_hour: float = 50.0      # how fast it gets hungry
    energy_per_hour: float = 18.0      # how fast it tires while awake
    xp_per_handshake: float = 12.0     # XP for catching an AP-monster
    xp_per_pmkid: float = 7.0
    xp_per_meter: float = 0.15         # walking = exercise = xp
    xp_per_snack: float = 2.0          # XP from eating a foraged snack
    energy_per_meter: float = 0.02
    base_xp: float = 120.0             # xp_to_next = base_xp * level**level_exp
    level_exp: float = 1.6
    # foraging: walking is how the pet finds FOOD (and, rarely, gear)
    forage_food: float = 12.0          # hunger restored per foraged snack
    forage_food_per_m: float = 0.06    # snack chance per metre walked (capped)
    forage_gear_per_m: float = 0.0016  # gear-find chance per metre walked (capped)

    # ai backend: "canned" (no deps) | "cpu" (llama.cpp) | "npu" (RKLLM, future)
    ai_backend: str = "canned"
    ai_model_path: str = ""

    # gps: "sim" (random wander) | "gpsd" (real device) | "off"
    gps_mode: str = "sim"
    gpsd_host: str = "127.0.0.1"
    gpsd_port: int = 2947

    # --- RPG: monsters, battles, cracking ---
    bestiary_path: str = "~/.flippergotchi/bestiary.json"
    ledger_path: str = "~/.flippergotchi/ledger.json"
    prefs_path: str = "~/.flippergotchi/prefs.json"
    peers_path: str = "~/.flippergotchi/peers.json"
    inventory_path: str = "~/.flippergotchi/inventory.json"
    quests_path: str = "~/.flippergotchi/quests.json"
    achievements_path: str = "~/.flippergotchi/achievements.json"
    wallet_path: str = "~/.flippergotchi/wallet.json"     # "scrap" currency balance
    element: str = "Aether"            # your Flippergotchi's element (duel matchups)
    scan_bluetooth: bool = True
    bluetooth_scan_timeout: float = 2.5
    # BLE "tame": actively connect + enumerate GATT (services/chars) for a
    # richer catch. Active, so gated to authorized scope like deauth/crack.
    ble_enum: bool = True              # allow GATT enumeration on authorized BLE
    ble_tame_timeout: float = 8.0      # GATT connect/enumerate timeout (s)
    # unwanted-tracker (AirTag/Tile) detection -- a safety feature
    tracker_log_path: str = "~/.flippergotchi/trackers.json"
    tracker_alert_sightings: int = 4   # distinct sightings before a stalker alert
    tracker_alert_window_s: float = 120.0  # min time spread across sightings
    duel_stake_frac: float = 0.20            # share of handshakes the loser forfeits
    duel_turn_cap: int = 30                  # max turns before HP-based decision
    # cracking is ONLY allowed against networks matching these (ssid/bssid
    # substrings) - your own "dojo". Empty => battles are refused by default.
    home_networks: list = field(default_factory=list)
    hashcat_bin: str = "hashcat"
    wordlist: str = "/usr/share/wordlists/rockyou.txt"
    wordlists: list = field(default_factory=list)  # ordered; overrides `wordlist`
    hashcat_rules: str = ""            # optional hashcat .rule file (-r)
    crack_timeout: int = 1800          # hashcat wall-clock cap (s)
    handshakes_file: str = ""          # bettercap wifi.handshakes.file (live)
    cloud_enabled: bool = False              # allow upload fallback on hard targets
    cloud_service: str = "wpa-sec"           # wpa-sec | onlinehashcrack
    cloud_timeout: int = 30                  # HTTP timeout for cloud up/download
    # wpa-sec (https://wpa-sec.stanev.org) -- the validated cloud path. Your API
    # key is the "key" cookie from your wpa-sec account.
    wpa_sec_url: str = "https://wpa-sec.stanev.org/"
    wpa_sec_key: str = ""
    # onlinehashcrack -- generic multipart uploader to a configurable endpoint
    # (their API has changed over time; NEEDS VALIDATION against the live service)
    onlinehashcrack_url: str = "https://api.onlinehashcrack.com/v2"
    onlinehashcrack_key: str = ""

    # --- WiFi capture stack (core/wifi) ---
    # backend: "auto" picks native (hcxdumptool/scapy) -> bettercap -> sim
    capture_backend: str = "auto"            # auto | native | bettercap | sim
    # dry_run: drive the REAL hardware paths (monitor mode, scan, passive
    # listen, validation, command-building) but suppress the two irreversible/
    # expensive actions -- deauth INJECTION and actually running hashcat. For
    # validating the stack on a monitor-mode dongle without attacking anything.
    dry_run: bool = False
    capture_timeout: int = 20          # seconds to listen per capture attempt
    channels: list = field(default_factory=list)   # explicit hop list (empty = full plan)
    capture_dir: str = "~/.flippergotchi/captures"
    regdomain: str = ""                # `iw reg set` country code (e.g. "AU")
    deauth_count: int = 5              # deauth frames per authorized capture nudge
    # authorization + audit (active RF actions are gated to your dojo)
    allowlist_path: str = "~/.flippergotchi/allowlist.txt"  # extra BSSID/SSID scope
    audit_log: str = "~/.flippergotchi/audit.log"           # JSONL of active actions
    # "home" = where battling is offered: geofence and/or a home network in range
    home_location: list = field(default_factory=list)  # [lat, lon]
    home_radius_m: float = 80.0
    anim_delay: float = 0.18                  # seconds between encounter frames (TUI)
    encounter_cooldown: int = 5               # ticks before re-encountering an AP

    # view / io
    tui: bool = True
    manual: bool = False               # prompt [A]Capture/[B]Run per encounter
    character_variant: str = "classic"       # shark colour: classic|blue|tiger|gold|reef
    flipctl_html_out: str = "/tmp/flippergotchi/face.html"
    battle_html_out: str = "/tmp/flippergotchi/battle.html"
    equip_html_out: str = "/tmp/flippergotchi/equip.html"
    encounter_html_out: str = "/tmp/flippergotchi/encounter.html"
    capture_frames_dir: str = "/tmp/flippergotchi/capture"  # net-gun anim frames
    battlemenu_html_out: str = "/tmp/flippergotchi/battlemenu.html"  # dojo menu
    battlelist_html_out: str = "/tmp/flippergotchi/battlelist.html"  # target list
    state_path: str = "~/.flippergotchi/state.json"

    @classmethod
    def load(cls, path: str | None) -> "Config":
        cfg = cls()
        if not path:
            return cfg
        p = os.path.expanduser(path)
        if not os.path.exists(p):
            return cfg
        if tomllib is not None:
            with open(p, "rb") as f:
                data = tomllib.load(f)
        else:
            with open(p) as f:
                data = _parse_toml_lite(f.read())
        names = {fld.name for fld in fields(cls)}
        for k, v in data.items():
            if k in names:
                setattr(cfg, k, v)
        return cfg
