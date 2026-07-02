from __future__ import annotations

import os
from dataclasses import dataclass, field, fields

try:
    import tomllib  # py3.11+
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None


# The built-in home for all persistent state. Per-store paths default under this
# directory; overriding `state_dir` (config field) relocates every default path
# coherently (see Config.resolve_path / Config.apply_state_dir).
_DEFAULT_STATE_DIR = "~/.flippergotchi"


def _concrete_base() -> str:
    """A concrete state base to use when HOME is unavailable (e.g. under systemd
    with no HOME set, where os.path.expanduser('~') returns a literal '~').

    Prefers systemd's $STATE_DIRECTORY (set by `StateDirectory=flippergotchi`),
    falling back to the FHS state location. Never returns a '~'-relative path."""
    sd = os.environ.get("STATE_DIRECTORY", "")
    sd = sd.split(os.pathsep)[0].strip() if sd else ""
    return sd or "/var/lib/flippergotchi"


def _safe_expanduser(value: str) -> str:
    """expanduser that never yields a literal '~'. When HOME is unset the stdlib
    leaves a leading '~' in place; anchor that tail under a concrete base so
    state can never land in './~/...' relative to the process CWD."""
    p = os.path.expanduser(str(value))
    if p == "~" or p.startswith("~" + os.sep) or p.startswith("~/"):
        tail = p[1:].lstrip("/\\")
        return os.path.join(_concrete_base(), tail) if tail else _concrete_base()
    return p


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
    # REST API basic-auth (live mode). Unset by default -- set these to match
    # your bettercap `api.rest` config; shipping real creds is a bad default.
    bettercap_user: str = ""
    bettercap_pass: str = ""

    # tamagotchi mechanics
    hunger_per_hour: float = 50.0      # how fast it gets hungry
    energy_per_hour: float = 18.0      # how fast it tires while awake
    xp_per_handshake: float = 12.0     # XP for catching an AP-monster
    xp_per_pmkid: float = 7.0
    xp_per_meter: float = 0.15         # walking = exercise = xp
    xp_per_snack: float = 0.5          # XP from eating a foraged snack (small: eating isn't a grind)
    energy_per_meter: float = 0.02
    base_xp: float = 120.0             # xp_to_next = base_xp * level**level_exp
    # Gentler growth curve (was 1.6): with two new mid-game stages (adult L14,
    # prime L20) an evolution now lands ~weekly through month 1 and a committed
    # player reaches legend (L40, ~339k cumulative XP) in ~4-6 weeks, not ~1.3yr.
    level_exp: float = 1.4
    # --- post-L40 paragon (non-destructive prestige) ---
    # Levelling continues past 40; every `paragon_every` levels past
    # `paragon_start_level` grants one paragon marker. NO level reset.
    paragon_start_level: int = 40
    paragon_every: int = 10
    # --- soft stakes: non-lethal "sick"/sulking neglect state (NORMAL mode) ---
    # Sustained neglect makes the pet sick: XP gain stalls, foraging is refused
    # and happiness is capped -- but health is never touched, so it CANNOT die.
    # (Hardcore is unchanged: it uses starvation-death instead of sickness.)
    sick_hunger_threshold: float = 85.0   # hunger at/above this counts as neglect
    sick_onset_hours: float = 6.0         # cumulative neglect before falling sick
    sick_recover_hunger: float = 45.0     # feed hunger to/below this to recover
    sick_happiness_cap: float = 20.0      # happiness is capped here while sick
    # sleep/energy: the pet naps when energy is low and wakes once rested
    sleep_energy_low: float = 20.0        # nap when energy drops to/below this
    wake_energy_high: float = 80.0        # wake once energy recovers to/above this
    # auto-duels: the loop occasionally duels a detected peer (a payoff beat, not
    # the heartbeat), only when the matchup is competitive (odds in [min,max]).
    auto_duel_cooldown: int = 120         # min ticks between auto-duels
    auto_duel_chance: float = 0.05        # per-tick chance once off cooldown
    auto_duel_min_odds: float = 0.2       # skip a peer you'd almost surely lose to
    auto_duel_max_odds: float = 0.85      # skip a peer you'd almost surely stomp
    onboard_quiet_catches: int = 5        # suppress pentest jargon for the first N catches
    # foraging: walking is how the pet finds FOOD (and, rarely, gear)
    forage_food: float = 12.0          # hunger restored per foraged snack (untyped)
    forage_food_per_m: float = 0.01    # snack chance per metre walked (capped) — periodic reward, not a firehose
    forage_gear_per_m: float = 0.0016  # gear-find chance per metre walked (capped)
    # larder: foraged food is stashed (not auto-eaten) while hunger is below this;
    # at/above it -- or when the larder is full -- the forage is eaten on the spot
    larder_path: str = "~/.flippergotchi/larder.json"
    larder_capacity: int = 20
    forage_auto_eat_hunger: float = 80.0  # only auto-eat when genuinely hungry; below this, stash to the larder

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
    crackle_bin: str = "crackle"       # BLE pairing cracker (LE Legacy Pairing)
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
    audit_log: str = "~/.flippergotchi/audit.log"           # JSONL of active actions
    # "home" = where battling is offered: geofence and/or a home network in range
    home_location: list = field(default_factory=list)  # [lat, lon]
    home_radius_m: float = 80.0
    anim_delay: float = 0.18                  # seconds between encounter frames (TUI)
    encounter_cooldown: int = 5               # ticks before re-encountering an AP

    # view / io
    tui: bool = True
    manual: bool = False               # prompt [A]Capture/[B]Run per encounter
    character_variant: str = "classic"       # shark species: classic|hammerhead|goblin|sawshark|whaleshark
    flipctl_html_out: str = "/tmp/flippergotchi/face.html"
    battle_html_out: str = "/tmp/flippergotchi/battle.html"
    equip_html_out: str = "/tmp/flippergotchi/equip.html"
    encounter_html_out: str = "/tmp/flippergotchi/encounter.html"
    feed_html_out: str = "/tmp/flippergotchi/feed.html"            # feeding screen
    badge_html_out: str = "/tmp/flippergotchi/badges.html"         # achievement wall
    capture_frames_dir: str = "/tmp/flippergotchi/capture"  # net-gun anim frames
    battlemenu_html_out: str = "/tmp/flippergotchi/battlemenu.html"  # dojo menu
    battlelist_html_out: str = "/tmp/flippergotchi/battlelist.html"  # target list
    blebattle_frames_dir: str = "/tmp/flippergotchi/blebattle"       # BLE anim frames
    # Root for all persistent state. Every *_path default lives under here; move
    # this (config or $FLIPPERGOTCHI_CONFIG) to relocate ALL state together.
    state_dir: str = "~/.flippergotchi"
    state_path: str = "~/.flippergotchi/state.json"

    @staticmethod
    def _search_config_path() -> str | None:
        """Default config search path when none is passed explicitly. Returns the
        first candidate that exists, else None (=> pure defaults). Order:
        $FLIPPERGOTCHI_CONFIG, ./flippergotchi.toml, ~/.config/flippergotchi/
        config.toml, /etc/flippergotchi/config.toml."""
        candidates = []
        env = os.environ.get("FLIPPERGOTCHI_CONFIG")
        if env:
            candidates.append(env)
        candidates += [
            "flippergotchi.toml",
            "~/.config/flippergotchi/config.toml",
            "/etc/flippergotchi/config.toml",
        ]
        for c in candidates:
            if c and os.path.exists(os.path.expanduser(c)):
                return c
        return None

    @classmethod
    def load(cls, path: str | None) -> "Config":
        # No explicit path -> consult the default search path so the device can
        # run without `-c`. An explicit path keeps its exact prior behaviour.
        if not path:
            path = cls._search_config_path()
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

    def _state_base_dir(self) -> str:
        """The concrete directory `state_dir` resolves to (HOME-unset safe).

        When HOME is unset the default ``~/.flippergotchi`` cannot expand, so the
        concrete base (``$STATE_DIRECTORY`` or ``/var/lib/flippergotchi``)
        replaces the whole ``~/...`` state root -- not just the leading ``~`` --
        keeping the resulting tree clean (``/var/lib/flippergotchi/state.json``,
        not ``.../.flippergotchi/state.json``)."""
        base = os.path.expanduser(str(self.state_dir))
        if base == "~" or base.startswith("~" + os.sep) or base.startswith("~/"):
            base = _concrete_base()
        return base

    def resolve_path(self, value: str) -> str:
        """Resolve a per-store path to a concrete filesystem location.

        (a) A path still at its *default* location (under the built-in
            ``~/.flippergotchi``) is relocated under ``state_dir`` -- so
            overriding ``state_dir`` moves ALL state coherently.
        (b) ``~`` is expanded and can never yield a literal ``~``: with HOME
            unset (systemd) it anchors under a concrete base instead of creating
            ``./~/.flippergotchi`` in the process CWD.

        An explicitly-set path (anything not under the default base -- e.g. the
        tmp paths the test suite injects) is passed through unchanged apart from
        the same HOME-unset-safe ``~`` expansion.
        """
        value = str(value)
        base = self._state_base_dir()
        if value == _DEFAULT_STATE_DIR:
            return base
        if value.startswith(_DEFAULT_STATE_DIR + "/"):
            return os.path.join(base, value[len(_DEFAULT_STATE_DIR) + 1:])
        return _safe_expanduser(value)

    def apply_state_dir(self) -> "Config":
        """Rewrite every state-bearing path field in place to a concrete location
        under ``state_dir`` (see resolve_path). Only fields whose *default* lives
        under ``~/.flippergotchi`` are touched -- ephemeral render outputs
        (``/tmp/...``) and non-path fields are left alone. Call once after load;
        safe to call again (idempotent for already-resolved paths)."""
        for fld in fields(self):
            default = fld.default
            if isinstance(default, str) and default.startswith(_DEFAULT_STATE_DIR):
                setattr(self, fld.name, self.resolve_path(getattr(self, fld.name)))
        return self
