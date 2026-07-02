"""BLE signal-sprite mechanics: "befriend" (tame) rewards + unwanted-tracker
safety detection.

Two-tier collection mirrors the WiFi capture->crack split:
  * scanning an advertisement = a *sighting* (lightly collected), handled in
    ``monsters.from_ble``;
  * an active GATT enumerate = a *befriend* (the real catch) -> ``tame_reward``.

``TrackerLog`` is the anti-stalking heuristic and a genuine safety feature: if a
real tracker (an AirTag/Tile-style device) keeps showing up around *you* across a
spread of time, we warn *you* it may be following you. That's a protective alert
about a stalker device, and in-game a rare "stalker" encounter -- never about
exploiting anyone else.
"""
from __future__ import annotations

import json
import os
import time

# Internal reward matcher (NOT surfaced to the player): the more a sprite's
# advertisement offers up, the chattier/richer it is, so the bigger the keepsake.
# These are raw GATT service-name substrings matched against real adverts.
_JUICY = ("device_information", "heart_rate", "audio_sink", "glucose",
          "human_interface_device", "find_my", "tile", "battery_service")


def tame_summary(enum_result: dict) -> str:
    e = enum_result or {}
    return f"{len(e.get('services') or [])} services / {int(e.get('characteristics', 0) or 0)} chars"


def tame_reward(monster, enum_result: dict) -> dict:
    """XP + scrap from a successful GATT enumeration; richer device = more."""
    svcs = (enum_result or {}).get("services") or []
    chars = int((enum_result or {}).get("characteristics", 0) or 0)
    n = len(svcs)
    juicy = sum(1 for s in svcs if any(j in str(s).lower() for j in _JUICY))
    rare = getattr(monster, "rarity", "") == "rare"
    return {
        "xp": 6 + n * 2 + juicy * 3,
        "scrap": 10 + n * 4 + (20 if rare else 0),
        "services": n, "chars": chars, "key": tame_summary(enum_result),
    }


class TrackerLog:
    """Persistent log of tracker sightings; flags one that follows you."""

    def __init__(self, path: str):
        self.path = os.path.expanduser(path)
        self._seen: dict = {}
        self._alerted: set = set()
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            raw = json.load(open(self.path))
            if isinstance(raw, dict):
                self._seen = raw.get("seen", {}) or {}
                self._alerted = set(raw.get("alerted", []) or [])
        except Exception:  # noqa: BLE001
            self._seen, self._alerted = {}, set()

    def save(self) -> None:
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = f"{self.path}.tmp.{os.getpid()}"
        with open(tmp, "w") as f:
            json.dump({"seen": self._seen, "alerted": sorted(self._alerted)}, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    def record(self, addr: str, name: str = "", now: float | None = None) -> None:
        now = float(now if now is not None else time.time())
        e = self._seen.get(addr)
        if e is None:
            self._seen[addr] = {"count": 1, "first": now, "last": now, "name": name}
        else:
            e["count"] = int(e.get("count", 0)) + 1
            e["last"] = now
            e.setdefault("first", now)   # backfill on a partial/edited entry
            if name:
                e["name"] = name

    def is_stalker(self, addr: str, cfg) -> bool:
        e = self._seen.get(addr)
        if not isinstance(e, dict):
            return False
        need = int(getattr(cfg, "tracker_alert_sightings", 4) or 4)
        window = float(getattr(cfg, "tracker_alert_window_s", 120.0) or 120.0)
        # defensive reads: a corrupt/hand-edited entry must not crash this safety
        # check (it's the anti-stalking alert), so missing fields read as 0.
        count = int(e.get("count", 0) or 0)
        span = float(e.get("last", 0) or 0) - float(e.get("first", 0) or 0)
        return count >= need and span >= window

    def should_alert(self, addr: str, cfg) -> bool:
        """True exactly once -- when a tracker first qualifies as a stalker."""
        if addr in self._alerted:
            return False
        if self.is_stalker(addr, cfg):
            self._alerted.add(addr)
            return True
        return False
