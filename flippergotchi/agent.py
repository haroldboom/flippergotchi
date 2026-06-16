from __future__ import annotations

import os
import time

from . import persistence
from .ai.service import AIService
from .core.bettercap import BettercapClient
from .core.bluetooth import BluetoothScanner
from .game import encounter, monsters
from .game.bestiary import Bestiary
from .pet import mechanics
from .pet.gps import GpsReader
from .view import animations, flipctl, tui


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
        self._tick_i = 0
        self._cooldown = {}      # bssid -> tick last encountered
        self._visible = []       # recently-seen SSIDs (for 'home' detection)

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

    def _scene(self, text: str) -> None:
        os.system("clear")
        print(text)

    def _note_visible(self, ssid: str) -> None:
        if ssid and ssid not in self._visible:
            self._visible.append(ssid)
            self._visible = self._visible[-20:]

    def _encounter(self, ev: dict) -> None:
        bssid, ssid = ev.get("bssid", "?"), ev.get("ssid", "?")
        if not monsters.is_valid_id(bssid):
            return  # can't uniquely track this AP
        self._note_visible(ssid)
        last = self._cooldown.get(bssid)
        if last is not None and self._tick_i - last < self.cfg.encounter_cooldown:
            return
        self._cooldown[bssid] = self._tick_i

        self.state.networks_seen += 1
        m = monsters.from_ap(ev)
        enc = encounter.Encounter(m)
        if self.cfg.tui:
            self._scene(animations.popup(m))
            time.sleep(self.cfg.anim_delay * 2)

        enc.choose(encounter.auto_choice(m))   # device: choice comes from a button
        if self.cfg.tui:
            animations.play(animations.frames(enc.animation, m),
                            self._scene, self.cfg.anim_delay)

        if enc.state == encounter.CAUGHT:
            self.dex.add(m)
            ups = mechanics.feed(self.state, "handshake", self.cfg)  # handshake = food
            self._fx_set("eating")
            self.log(f"[catch] {m.species} '{ssid}' Lv{m.level} "
                     f"[{m.encryption}] -- {self.ai.analyze(ev)}")
            self.speak("fed", ssid, "handshake")
            self._progress(ups)
        elif enc.state == encounter.ESCAPED:
            m.captured = False
            self.dex.add(m)
            self.log(f"[escape] {ssid} broke free - no handshake")
        else:  # FLED
            self.log(f"[run] fled from {m.species} '{ssid}'")

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
                self._encounter(ev)

    def tick(self, dt: float) -> None:
        self._tick_i += 1
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
