from __future__ import annotations

import time

from . import persistence
from .ai.service import AIService
from .core.bettercap import BettercapClient
from .core.bluetooth import BluetoothScanner
from .game import monsters
from .game.bestiary import Bestiary
from .pet import mechanics
from .pet.gps import GpsReader
from .view import flipctl, tui


class Agent:
    """The main loop: capture -> feed/walk -> decay -> speak -> render."""

    def __init__(self, cfg, state):
        self.cfg = cfg
        self.state = state
        self.wifi = BettercapClient(cfg)
        self.ble = BluetoothScanner(cfg) if cfg.scan_bluetooth else None
        self.gps = GpsReader(cfg)
        self.ai = AIService(cfg)
        self.dex = Bestiary(cfg.bestiary_path)
        self._say = ""
        self._fx = None          # (mood, until_ts) transient face override
        self._last_save = 0.0
        self._last_idle = 0.0

    def log(self, msg: str) -> None:
        print(f"· {msg}")

    def speak(self, event_key: str, arg: str = "", sub: str = "") -> None:
        self._say = self.ai.speak(event_key, self.state, arg, sub)
        if not self.cfg.tui:
            self.log(f"({self.state.name}) {self._say}")

    def _fx_set(self, mood: str, secs: float = 3.0) -> None:
        self._fx = (mood, time.time() + secs)

    def _fx_mood(self) -> str | None:
        if self._fx and time.time() < self._fx[1]:
            return self._fx[0]
        return None

    def _progress(self, ups: list) -> None:
        for u in ups:
            if u.get("type") != "level_up":
                continue
            if "evolved_to" in u:
                self.log(f"** evolved into {u['evolved_to']} **")
                self.speak("evolved", u["evolved_to"])
            else:
                self.log(f"** level up -> {u['level']} **")
                self.speak("level_up", str(u["level"]))
            self._fx_set("excited")

    def _spawn_wifi(self, ev: dict, captured: bool) -> None:
        m = monsters.from_ap(ev)
        m.captured = m.captured or captured
        new = self.dex.add(m)
        if not new:
            return
        if captured:
            self.log(f"[dex] CAUGHT {m.species} '{m.name}' Lv{m.level} "
                     f"[{m.encryption}] -- {self.ai.analyze(ev)}")
        else:
            self.log(f"[dex] a wild {m.species} '{m.name}' appeared (Lv{m.level})")

    def _spawn_ble(self) -> None:
        if not self.ble:
            return
        for ev in self.ble.poll():
            m = monsters.from_ble(ev)
            if self.dex.add(m):
                self.state.happiness = mechanics.clamp(self.state.happiness + 1)
                self.log(f"[dex] a tiny {m.species} '{m.name}' blipped past (Lv{m.level})")

    def _events(self, events: list) -> None:
        for ev in events:
            if ev.get("type") == "ap":
                self.state.networks_seen += 1
                self._spawn_wifi(ev, captured=False)
            elif ev.get("type") == "handshake":
                kind = ev.get("kind", "handshake")
                ssid = ev.get("ssid", "?")
                ups = mechanics.feed(self.state, kind, self.cfg)
                self.log(f"captured {kind} from {ssid} ({ev.get('bssid', '?')})")
                self._fx_set("eating")
                self.speak("fed", ssid, kind)
                self._spawn_wifi(ev, captured=True)
                self._progress(ups)

    def tick(self, dt: float) -> None:
        self._events(self.wifi.poll())
        self._spawn_ble()
        meters = self.gps.distance()
        if meters > 0:
            self._progress(mechanics.walk(self.state, meters, self.cfg))
        mechanics.tick(self.state, dt * self.cfg.time_scale, self.cfg)
        # occasional mood-driven chatter when nothing else is happening
        now = time.time()
        if now - self._last_idle > 20:
            m = mechanics.mood(self.state)
            if m in ("hungry", "sick", "tired", "happy", "sleeping"):
                self.speak(m)
            self._last_idle = now

    def render(self) -> None:
        override = self._fx_mood()
        if self.cfg.tui:
            tui.render(self.state, self.cfg, self._say, override)
        try:
            flipctl.render(self.state, self.cfg, self._say, override)
        except Exception as e:
            self.log(f"flipctl render failed: {e}")

    def run(self, ticks: int | None = None) -> None:
        if self.wifi.mode == "live":
            try:
                self.wifi.start()
            except NotImplementedError as e:
                self.log(f"can't start live capture: {e}")
                self.log("tip: pass --simulate to run without a radio.")
                return
        self.log(f"{self.state.name} waking up "
                 f"(stage={self.state.stage}, ai={self.ai.backend.name})")
        i, last = 0, time.time()
        try:
            while ticks is None or i < ticks:
                now = time.time()
                self.tick(now - last)
                last = now
                self.render()
                if now - self._last_save > 10:
                    persistence.save(self.cfg.state_path, self.state)
                    self.dex.save()
                    self._last_save = now
                i += 1
                time.sleep(self.cfg.tick_interval)
        except KeyboardInterrupt:
            self.log("going to sleep... (saving state)")
        finally:
            persistence.save(self.cfg.state_path, self.state)
            self.dex.save()
