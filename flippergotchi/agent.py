from __future__ import annotations

import os
import time

from . import persistence
from . import prefs as prefs_mod
from .ai.service import AIService
from .core.authz import Authorizer
from .core.bluetooth import BluetoothScanner
from .core.wifi.backends import make_backend
import random

from .game import encounter, equipment, monsters
from .game import quests as quests_mod
from .game import shop as shop_mod
from .game.achievements import AchievementBook
from .game.bestiary import Bestiary
from .game.home import at_home
from .game.quests import QuestLog
from .game.shop import Wallet
from .pet import mechanics
from .pet.gps import GpsReader
from .view import animations, flipctl, tui


class Agent:
    """The main loop: capture -> feed/walk -> decay -> speak -> render."""

    def __init__(self, cfg, state):
        self.cfg = cfg
        self.state = state
        # active RF actions (deauth/capture) are gated to your authorized dojo
        self.authz = Authorizer(cfg)
        self.wifi = make_backend(cfg, is_authorized=self.authz.is_authorized)
        self.ble = BluetoothScanner(cfg) if cfg.scan_bluetooth else None
        self.gps = GpsReader(cfg)
        self.ai = AIService(cfg)
        self.dex = Bestiary(cfg.bestiary_path)
        self.inv = equipment.Inventory(cfg.inventory_path)
        self.quests = QuestLog(cfg.quests_path)
        self.book = AchievementBook(getattr(cfg, "achievements_path",
                                            "~/.flippergotchi/achievements.json"))
        self.wallet = Wallet(getattr(cfg, "wallet_path",
                                     "~/.flippergotchi/wallet.json"))
        self._say = ""
        self._fx = None          # (mood, until_ts) transient face override
        self._last_save = 0.0
        self._last_idle = 0.0
        self._tick_i = 0
        self._cooldown = {}      # bssid -> tick last encountered
        self._visible = []       # recently-seen SSIDs (for 'home' detection)
        self._was_home = False   # for the one-shot "you're home" battle prompt
        self._peers = prefs_mod.load(cfg.peers_path)  # addr -> peer Flippergotchi

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

    def _choose(self, m) -> str:
        """Capture/Run decision. Manual mode asks you; otherwise auto-policy."""
        if self.cfg.manual:
            try:
                ans = input(f"  wild {m.species} '{m.name}' Lv{m.level} "
                            "[A]Capture / [B]Run > ").strip().lower()
                return "run" if ans.startswith("b") or ans == "run" else "capture"
            except (EOFError, KeyboardInterrupt):
                pass
        return encounter.auto_choice(m)

    def _quest(self, metric: str, amount: float) -> None:
        for q in self.quests.record(metric, amount):
            reward = quests_mod.grant_quest_reward(q, self.state, self.inv, self.cfg)
            self.log(f"[quest] DONE: {q.description} -> {reward}")
            self._fx_set("excited")

    def _achievements(self) -> None:
        """Unlock any newly-met badges; grant their small rewards. Cheap enough
        to call after each catch/walk. Never raises out of the loop."""
        try:
            stats = {
                "catches": sum(1 for x in self.dex.all()
                               if getattr(x, "captured", False)),
                "cracks": 0,            # cracking happens via the `battle` command
                "duel_wins": getattr(self.state, "duel_wins", 0),
                "distance_m": getattr(self.state, "distance_m", 0.0),
                "level": self.state.level,
                "stage": self.state.stage,
                "equipped_slots": len(getattr(self.inv, "equipped", {}) or {}),
                "shinies": 0,
            }
            for b in self.book.check(stats):
                rw = b.reward or {}
                self.wallet.earn(int(rw.get("scrap", 0)))
                for _ in range(int(rw.get("food", 0))):
                    mechanics.snack(self.state, self.cfg)
                self.log(f"[badge] ★ {b.name} -- {b.description}")
                self._fx_set("excited")
        except Exception as e:  # noqa: BLE001 - never break the tick loop
            self.log(f"achievement check failed: {e}")

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
        self._render_encounter(m)
        if self.cfg.tui:
            self._scene(animations.popup(m))
            time.sleep(self.cfg.anim_delay * 2)

        enc.choose(self._choose(m))            # device: choice comes from a button
        if self.cfg.tui:
            animations.play(animations.frames(enc.animation, m),
                            self._scene, self.cfg.anim_delay)

        if enc.state in (encounter.CAUGHT, encounter.ESCAPED):
            self._render_capture(m, enc.state == encounter.CAUGHT)
        if enc.state == encounter.CAUGHT:
            self.dex.add(m)
            ups = mechanics.collect(self.state, "handshake", self.cfg)  # catch it
            self._fx_set("excited")
            self.log(f"[catch] caught {m.species} '{ssid}' Lv{m.level} "
                     f"[{m.encryption}] -- {self.ai.analyze(ev)}")
            self.speak("caught", ssid)
            self._quest("catches", 1)
            self.wallet.earn(shop_mod.scrap_for_catch())
            self._achievements()
            self._progress(ups)
        elif enc.state == encounter.ESCAPED:
            m.captured = False
            self.dex.add(m)
            self.log(f"[escape] {ssid} broke free - no handshake")
        else:  # FLED
            self.log(f"[run] fled from {m.species} '{ssid}'")

    def _render_encounter(self, m) -> None:
        """Best-effort visual encounter card to cfg.encounter_html_out."""
        try:
            from .view import encounter_screen
            out = getattr(self.cfg, "encounter_html_out",
                          "/tmp/flippergotchi/encounter.html")
            encounter_screen.render(os.path.expanduser(out), {
                "species": m.species, "name": monsters.label(m), "level": m.level,
                "encryption": m.encryption, "defense": m.defense, "kind": m.kind,
            })
        except Exception as e:  # noqa: BLE001 - never break the tick loop
            self.log(f"encounter render failed: {e}")

    def _render_capture(self, m, caught: bool) -> None:
        """Best-effort visual net-gun capture frames to cfg.capture_frames_dir.

        The HUD shows the live deauth/capture settings (the values the real
        capture path uses)."""
        try:
            from .view import capture_screen
            out = getattr(self.cfg, "capture_frames_dir",
                          "/tmp/flippergotchi/capture")
            variant = getattr(self.cfg, "character_variant", "classic")
            player = (self.state.stage if variant in ("classic", "")
                      else f"{variant}-{self.state.stage}")
            capture_screen.render_sequence(
                os.path.expanduser(out),
                {"species": m.species, "name": monsters.label(m)},
                caught=caught, player=player,
                timeout=int(getattr(self.cfg, "capture_timeout", 20) or 20),
                deauth=int(getattr(self.cfg, "deauth_count", 5) or 5))
        except Exception as e:  # noqa: BLE001 - never break the tick loop
            self.log(f"capture render failed: {e}")

    def _forage(self, meters: float) -> None:
        """Walking is how the pet finds FOOD (and, rarely, gear)."""
        if random.random() < min(0.9, meters * self.cfg.forage_food_per_m):
            self._fx_set("eating")
            self.log("[forage] nibbled a snack found on the walk")
            self.speak("fed", "snack")
            self._progress(mechanics.snack(self.state, self.cfg))
            self._quest("snacks", 1)
        if random.random() < min(0.5, meters * self.cfg.forage_gear_per_m):
            it = self.inv.add(equipment.roll_item(boost=self.state.level // 3))
            self.log(f"[loot] foraged {it.rarity} gear: {it.name} (+{it.power} pow)")

    def _spawn_ble(self) -> None:
        if not self.ble:
            return
        for ev in self.ble.poll():
            if ev.get("type") == "peer":
                self._note_peer(ev)
                continue
            m = monsters.from_ble(ev)
            if self.dex.add(m):
                self.state.happiness = mechanics.clamp(self.state.happiness + 1)
                self.log(f"[dex] a tiny {m.species} '{m.name}' blipped past (Lv{m.level})")

    def _note_peer(self, ev: dict) -> None:
        addr = ev.get("addr")
        if not monsters.is_valid_id(addr):
            return
        first = addr not in self._peers
        self._peers[addr] = {"name": ev.get("name", "?"), "addr": addr,
                             "level": ev.get("level", 1),
                             "handshakes": ev.get("handshakes", 0),
                             "gear_power": ev.get("gear_power", 0),
                             "element": ev.get("element", "Aether")}
        if first:
            p = self._peers[addr]
            self.log(f"[peer] another Flippergotchi nearby: {p['name']} "
                     f"(Lv{p['level']}) -- duel it with `duel {p['name']}`")
            self._fx_set("excited")

    def _events(self, events: list) -> None:
        for ev in events:
            if ev.get("type") == "ap":
                self._encounter(ev)

    def tick(self, dt: float) -> None:
        self._tick_i += 1
        self.quests.roll(time.strftime("%Y-%m-%d"))   # daily quests (no-op same day)
        self._events(self.wifi.scan())
        self._spawn_ble()
        meters = self.gps.distance()
        if meters > 0:
            self._progress(mechanics.walk(self.state, meters, self.cfg))
            self._forage(meters)
            self._quest("distance_m", meters)
            self.wallet.earn(shop_mod.scrap_for_walk(meters))
            self._achievements()
        mechanics.tick(self.state, dt * self.cfg.time_scale, self.cfg)
        self._home_check()
        # occasional mood-driven chatter when nothing else is happening
        now = time.time()
        if now - self._last_idle > 20:
            m = mechanics.mood(self.state)
            if m in ("hungry", "sick", "tired", "happy", "sleeping"):
                self.speak(m)
            self._last_idle = now

    def _home_check(self) -> None:
        """One-shot 'you're home -> battle' prompt when you arrive home."""
        home = at_home(self.cfg, visible_ssids=self._visible)
        if home and not self._was_home:
            ready = sum(1 for x in self.dex.all()
                        if x.kind == "wifi" and x.captured and not x.defeated)
            if ready:
                self.log(f"[home] you're home -- {ready} monster(s) ready to "
                         f"battle. Run: flippergotchi battle --all")
        self._was_home = home

    def _equipped_map(self) -> dict:
        out = {}
        for slot, item_id in self.inv.equipped.items():
            it = self.inv.items.get(item_id)
            if it:
                out[slot] = it.rarity
        return out

    def render(self) -> None:
        override = self._fx_mood()
        if self.cfg.tui:
            tui.render(self.state, self.cfg, self._say, override)
        try:
            flipctl.render(self.state, self.cfg, self._say, override,
                           equipped=self._equipped_map())
        except Exception as e:
            self.log(f"flipctl render failed: {e}")

    def _save(self) -> None:
        persistence.save(self.cfg.state_path, self.state)
        self.dex.save()
        self.inv.save()
        self.quests.save()
        self.wallet.save()
        self.book.save()
        prefs_mod.save(self.cfg.peers_path, self._peers)

    def run(self, ticks: int | None = None) -> None:
        # backends are uniform: start() is a no-op in sim and self-degrades on
        # hardware errors, so it never raises out here.
        try:
            self.wifi.start()
        except Exception as e:  # noqa: BLE001
            self.log(f"capture backend start failed ({e}); continuing passive/sim.")
        backend = type(self.wifi).__name__
        self.log(f"{self.state.name} waking up "
                 f"(stage={self.state.stage}, ai={self.ai.backend.name}, "
                 f"capture={backend})")
        i, last = 0, time.time()
        try:
            while ticks is None or i < ticks:
                now = time.time()
                self.tick(now - last)
                last = now
                self.render()
                if now - self._last_save > 10:
                    self._save()
                    self._last_save = now
                i += 1
                time.sleep(self.cfg.tick_interval)
        except KeyboardInterrupt:
            self.log("going to sleep... (saving state)")
        finally:
            self._save()
