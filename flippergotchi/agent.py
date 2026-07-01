from __future__ import annotations

import os
import sys
import time

from . import persistence
from . import prefs as prefs_mod
from .ai.service import AIService
from .core.authz import Authorizer, in_scope
from .core.bluetooth import BluetoothScanner
from .core.wifi.backends import make_backend
from .sanitize import clean
import random

from .game import battle as battle_mod
from .game import ble as ble_mod
from .game import encounter, equipment, food, monsters
from .game import quests as quests_mod
from .game.larder import Larder
from .game import shop as shop_mod
from .game import achievements
from .game.achievements import AchievementBook
from .game.ble import TrackerLog
from .game.bestiary import Bestiary
from .game.home import WARNING, at_home
from .game.ledger import Ledger
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
        # prefs holds the dismissible active-ops consent (see _consented)
        self._prefs = prefs_mod.load(cfg.prefs_path)
        self._field_ack = None   # this-session on-the-fly consent (None=unasked)
        # active RF (deauth/injection) during a live capture is gated PER TARGET
        # by _capture_authorized: consent AND (manual pick | in-scope), so one
        # global "don't ask again" can't auto-deauth every AP in range.
        # Audits every active-RF decision the autonomous loop makes (deauth /
        # crack / active BLE), which otherwise leave no trail unlike the
        # standalone commands.
        self._authz = Authorizer(cfg)
        self.wifi = make_backend(cfg, is_authorized=self._capture_authorized)
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
        self.larder = Larder(getattr(cfg, "larder_path",
                                     "~/.flippergotchi/larder.json"),
                             getattr(cfg, "larder_capacity", 20))
        self.trackers = TrackerLog(getattr(cfg, "tracker_log_path",
                                           "~/.flippergotchi/trackers.json"))
        self.ledger = Ledger(cfg.ledger_path)
        self._say = ""
        self._fx = None          # (mood, until_ts) transient face override
        self._last_save = 0.0
        self._last_idle = 0.0
        self._tick_i = 0
        self._cooldown = {}      # bssid -> tick last encountered
        self._starve_warn = ("", 0)  # (last stage warned, tick warned) -- throttle
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
            reward = quests_mod.grant_quest_reward(q, self.state, self.inv,
                                                   self.cfg, self.wallet)
            self.log(f"[quest] DONE: {q.description} -> {reward}")
            self._fx_set("excited")
        bonus = self.quests.claim_daily_bonus(time.strftime("%Y-%m-%d"))
        if bonus:
            self.wallet.earn(bonus)
            self.log(f"[quest] all dailies cleared! +{bonus} scrap bonus")
            self._fx_set("excited")

    def _achievements(self) -> None:
        """Unlock any newly-met badges; grant their small rewards. Cheap enough
        to call after each catch/walk. Never raises out of the loop. Uses the
        shared build_stats so `cracks` is sourced from the live Ledger (was a
        hardcoded 0 here, so crack badges never unlocked in the agent loop)."""
        try:
            stats = achievements.build_stats(self.state, self.dex, self.inv,
                                             self.ledger, self.quests)
            for b in achievements.grant_reward(self.book, stats, self.state,
                                               self.cfg, self.wallet, self.inv):
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

        choice = self._choose(m)               # device: choice comes from a button
        if choice == "capture" and getattr(self.wifi, "name", "") in (
                "native", "bettercap"):
            # On a real capture backend, actually run the deauth + handshake
            # capture and let the radio decide the outcome. Sim never reaches
            # here (SimBackend.name == "sim"), so simulation is unchanged.
            captured, path = self._live_capture(ev)
            enc.resolve_capture(captured, path)
        else:
            enc.choose(choice)
        if self.cfg.tui:
            animations.play(animations.frames(enc.animation, m),
                            self._scene, self.cfg.anim_delay)

        if enc.state in (encounter.CAUGHT, encounter.ESCAPED):
            self._render_capture(m, enc.state == encounter.CAUGHT)
        if enc.state == encounter.CAUGHT:
            self.dex.add(m)
            # operate on the STORED instance: on a re-encounter add() merges into
            # the existing monster, so field-battle results (defeated/key) and the
            # capture_path must be written to the canonical object to persist.
            m = self.dex.get(m.id) or m
            ups = mechanics.collect(self.state, "handshake", self.cfg)  # catch it
            self._fx_set("excited")
            self.log(f"[catch] caught {m.species} '{clean(ssid)}' Lv{m.level} "
                     f"[{m.encryption}] -- {self.ai.analyze(ev)}")
            self.speak("caught", ssid)
            self._quest("catches", 1)
            self.wallet.earn(shop_mod.scrap_for_catch())
            self._achievements()
            self._progress(ups)
            # weak/legacy networks are crackable ON THE FLY -- no trip home.
            # CRACKING (WEP/WPA1) is the most sensitive action: gate it PER
            # TARGET (manual pick | in-scope) so one 'don't ask again' can't
            # auto-crack every weak network in range, THEN take the one-time
            # on-screen consent. Open just associates, so it needs neither.
            if m.encryption == "open":
                self._field_battle(m)
            elif m.encryption in ("wep", "wpa"):
                if not self._crack_in_scope(bssid, ssid):
                    self._authz.audit("crack", bssid, ssid, False,
                                      "AP out of authorized scope")
                    self.log(f"[skip] '{clean(ssid)}' is out of your authorized "
                             "scope -- caught but not cracked")
                elif self._field_consent():
                    self._authz.audit(
                        "crack", bssid, ssid, True,
                        "manual pick" if getattr(self.cfg, "manual", False)
                        else "in authorized scope")
                    self._field_battle(m)
        elif enc.state == encounter.ESCAPED:
            m.captured = False
            self.dex.add(m)
            self.log(f"[escape] {clean(ssid)} broke free - no handshake")
        else:  # FLED
            self.log(f"[run] fled from {m.species} '{clean(ssid)}'")

    def _render_encounter(self, m) -> None:
        """Best-effort visual encounter card to cfg.encounter_html_out."""
        try:
            from .view import encounter_screen
            out = getattr(self.cfg, "encounter_html_out",
                          "/tmp/flippergotchi/encounter.html")
            encounter_screen.render(os.path.expanduser(out), {
                "species": m.species, "name": monsters.label(m), "level": m.level,
                "encryption": m.encryption, "defense": m.defense, "kind": m.kind,
                "shiny": getattr(m, "shiny", False),
            })
        except Exception as e:  # noqa: BLE001 - never break the tick loop
            self.log(f"encounter render failed: {e}")

    def _consented(self, bssid: str = "", ssid: str = "") -> bool:
        """Has the player agreed to active operations (deauth/injection/GATT
        connect)? True once they tick 'don't ask again' on the crack warning.
        The session-wide consent flag -- no network allow-list."""
        return bool(self._prefs.get("hide_fieldcrack_warning"))

    def _capture_authorized(self, bssid: str = "", ssid: str = "") -> bool:
        """Per-target gate for ACTIVE deauth during a LIVE handshake capture,
        consulted by the capture backend. Every decision is audit-logged so the
        autonomous loop leaves the same tamper-evident trail as the standalone
        `capture` command."""
        allowed = self._capture_gate(bssid, ssid)
        if allowed:
            reason = ("consent + manual pick" if getattr(self.cfg, "manual", False)
                      else "consent + in authorized scope")
        else:
            reason = "no consent, or AP out of authorized scope"
        self._authz.audit("deauth", bssid, ssid, allowed, reason)
        return allowed

    def _capture_gate(self, bssid: str = "", ssid: str = "") -> bool:
        """The deauth decision (no audit): session consent AND a per-AP
        justification -- manual mode (the player picked this AP with a button)
        or the AP is in their optional authorized scope (cfg.home_networks).
        For every other AP the backend stays strictly passive, so one 'don't
        ask again' can't turn the auto loop into indiscriminate mass deauth of
        every network in range. Deny-by-default; passive capture is unaffected."""
        if not self._consented():
            return False
        if getattr(self.cfg, "manual", False):
            return True
        return in_scope(bssid, ssid, self.cfg)

    def _crack_in_scope(self, bssid: str = "", ssid: str = "") -> bool:
        """Per-target scope gate for ON-THE-FLY cracking, mirroring
        _capture_gate's per-AP justification: manual mode (the player picked
        this AP) or the AP is in cfg.home_networks. Deny-by-default, so a single
        'don't ask again' can't turn the auto loop into cracking every weak
        network in range -- cracking is the most sensitive action, so it gets
        the same scope discipline as deauth (it previously had none)."""
        if getattr(self.cfg, "manual", False):
            return True
        return in_scope(bssid, ssid, self.cfg)

    def _field_consent(self) -> bool:
        """One-time consent before cracking WEP/WPA on the fly -- the SAME
        warning as battling, with a 'don't ask again' that persists in prefs
        (no config files). Returns True if cracking-in-the-field is OK.

        Already ticked 'don't ask again' -> silent yes. Otherwise show the
        warning once; interactively the player chooses (and can dismiss it
        forever); non-interactively it stays paused until they confirm once."""
        if self._prefs.get("hide_fieldcrack_warning"):
            return True
        if self._field_ack is not None:      # already answered this session
            return self._field_ack
        print(WARNING)
        if not sys.stdin.isatty():
            print("  on-the-fly cracking is paused until you OK it once "
                  "(run interactively to confirm).")
            self._field_ack = False
            return False
        try:
            ans = input("  Crack WEP/WPA networks on the fly?  [y] yes  "
                        "[a] yes, don't ask again  [n] no > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            self._field_ack = False
            return False
        if ans.startswith("a"):
            self._prefs["hide_fieldcrack_warning"] = True
            prefs_mod.save(self.cfg.prefs_path, self._prefs)
            print("  [x] won't ask again.")
            self._field_ack = True
        else:
            self._field_ack = ans.startswith("y")
        return self._field_ack

    def _field_battle(self, m) -> None:
        """On-the-fly crack of a weak/legacy network (open/WEP/WPA1) -- no home
        trip needed. Authorization was already checked by the caller. Records to
        the ledger and rewards a win like the `battle` command. Guarded."""
        try:
            if m.encryption == "open":
                m.defeated, m.key = True, "(open)"
                self.ledger.record(m, "cracked", "open", "")
                self.log(f"[battle] walked into OPEN '{m.name}' -- no key needed")
            else:
                res = battle_mod.battle(
                    m, self.cfg, handshake_path=getattr(m, "capture_path", "") or None)
                self.ledger.record(m, res["result"], res.get("via", ""),
                                   res.get("key", ""))
                if res["result"] != "cracked":
                    self.log(f"[battle] {m.encryption.upper()} '{m.name}': "
                             f"{res['result']} ({res.get('via', '')})")
                    return
                self.log(f"[battle] cracked {m.encryption.upper()} '{m.name}' on "
                         f"the fly -- key: {res['key']} (via {res.get('via', '')})")
            # reward on a win (legendary WEP/WPA1 give a little extra scrap)
            bonus = 40 if getattr(m, "rarity", "") == "legendary" else 0
            self.wallet.earn(shop_mod.scrap_for_crack() + bonus)
            loot = self.inv.add(equipment.roll_item(boost=m.level // 2))
            self.log(f"[loot] {loot.rarity} {loot.name} (+{loot.power} pow)")
            self._quest("cracks", 1)
            if getattr(m, "rarity", "") == "legendary":
                self._quest("legendary_kills", 1)
            self._achievements()
            self._fx_set("excited")
        except Exception as e:  # noqa: BLE001 - never break the tick loop
            self.log(f"field battle failed: {e}")

    def _live_capture(self, ev: dict):
        """Run the REAL deauth + handshake capture via the backend and validate
        the result. Returns (captured: bool, path: str).

        Only called on a live capture backend (native/bettercap) -- sim never
        reaches here, so behaviour is unchanged without hardware. Fully guarded:
        any failure (no radio, timeout, bad capture) -> (False, ""). Active
        deauth is gated inside the backend by the Authorizer; capture is
        otherwise passive."""
        try:
            bssid = ev.get("bssid", "") or ""
            ssid = ev.get("ssid", "") or ""
            timeout = int(getattr(self.cfg, "capture_timeout", 20) or 20)
            path = self.wifi.capture_handshake(bssid, ssid, timeout=timeout)
            if not path:
                return False, ""
            from .core import handshake as hs
            info = hs.analyze_capture(path)
            # bool(info) == capture exists AND holds a PMKID / complete 4-way
            return bool(info), (path if bool(info) else "")
        except Exception as e:  # noqa: BLE001 - never break the tick loop
            self.log(f"live capture failed: {e}")
            return False, ""

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
                {"species": m.species, "name": monsters.label(m),
                 "shiny": getattr(m, "shiny", False)},
                caught=caught, player=player,
                timeout=int(getattr(self.cfg, "capture_timeout", 20) or 20),
                deauth=int(getattr(self.cfg, "deauth_count", 5) or 5))
        except Exception as e:  # noqa: BLE001 - never break the tick loop
            self.log(f"capture render failed: {e}")

    def _forage(self, meters: float) -> None:
        """Walking is how the pet finds FOOD (and, rarely, gear). A typed food is
        rolled; if the pet is genuinely hungry (or the larder is full) it eats on
        the spot (neglect play unchanged), otherwise it stashes it in the larder
        to hand-feed later."""
        if random.random() < min(0.9, meters * self.cfg.forage_food_per_m):
            kind = food.roll_forage(random)
            hungry = self.state.hunger >= self.cfg.forage_auto_eat_hunger
            if hungry or self.larder.is_full() or self.larder.add(kind.id) == 0:
                self._fx_set("eating")
                self.log(f"[forage] ate {kind.name} on the walk")
                self.speak("fed", "snack")
                self._progress(mechanics.snack(self.state, self.cfg, kind))
            else:
                self.log(f"[forage] stashed {kind.name} in the larder "
                         f"({self.larder.total()}/{self.larder.capacity})")
            self._quest("snacks", 1)
        # a well-fed pet forages luckier: satiety lifts the gear-find odds (PvP/
        # economy flavour only -- never touches cracking)
        luck = 1.0 + min(100.0, getattr(self.state, "satiety", 0.0)) / 100.0 * 0.5
        if random.random() < min(0.5, meters * self.cfg.forage_gear_per_m * luck):
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
            new = self.dex.add(m)
            canon = self.dex.get(m.id) or m   # the stored object (add merges)
            # unwanted-tracker (AirTag/Tile) detection -- a safety alert
            if ev.get("device_class") == "tracker" or canon.species == "Trackling":
                self.trackers.record(canon.id, canon.name)
                if self.trackers.should_alert(canon.id, self.cfg):
                    self.log(f"[ALERT] tracker '{canon.name}' ({canon.id}) keeps "
                             f"following you -- possible unwanted tracker!")
                    self._fx_set("sick")
            if new:
                self.state.happiness = mechanics.clamp(self.state.happiness + 1)
                tag = f" [{canon.rarity}]" if canon.rarity not in ("", "common") else ""
                self.log(f"[dex] a tiny {canon.species} '{canon.name}' blipped "
                         f"past (Lv{canon.level}{tag})")
            # deeper catch: actively enumerate GATT to fully tame it
            self._tame_ble(canon, ev)

    def _tame_ble(self, m, ev: dict) -> None:
        """Active GATT enumerate = the deeper 'tame' (richer reward). Sim runs a
        synthetic enumeration; on a live adapter it only connects when ble_enum
        is on AND the device is connectable AND in authorized scope (connecting
        is an active action). Guarded -- never breaks the tick loop."""
        if getattr(m, "defeated", False) or not ev.get("connectable", True):
            return
        if getattr(self.ble, "mode", "sim") != "sim":
            if not getattr(self.cfg, "ble_enum", True):
                return
            if not self._consented():   # connecting is active -> needs consent
                return
            # Active GATT connect on a real adapter -- audit it like deauth/crack.
            self._authz.audit("ble_enum", m.id, getattr(m, "name", ""), True,
                              "active GATT enumerate (consented)")
        try:
            result = self.ble.enumerate(m.id)
        except Exception as e:  # noqa: BLE001
            self.log(f"ble tame failed: {e}")
            return
        if not result:
            return
        # GATT enumerate is RECON -- it reveals the device + rewards scrap, but
        # does NOT defeat it. Owning a BLE monster is a *battle* (crack its
        # pairing / take control) via the Battle Dojo. Recording the recon on
        # last_result keeps it out of the "fresh" auto-battle pool only once
        # battled; here it stays battleable.
        reward = ble_mod.tame_reward(m, result)
        m.last_result = "interrogated"
        self.wallet.earn(reward["scrap"])
        self.state.happiness = mechanics.clamp(self.state.happiness + 2)
        self.log(f"[recon] interrogated {m.species} '{m.name}' -- {reward['key']} "
                 f"(+{reward['scrap']} scrap)  pairing={getattr(m, 'pairing', '?')}")
        self._quest("tames", 1)
        self._fx_set("excited")

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
        # The externally-driven work (radio scans, BLE polls, GPS-driven walk)
        # consumes data we don't control -- a single malformed AP/event from real
        # hardware must never kill the loop. Guard it; the deterministic decay +
        # death check below always run so the pet keeps ticking either way.
        try:
            self.quests.roll(time.strftime("%Y-%m-%d"))   # daily quests (no-op same day)
            self.quests.roll_weekly(time.strftime("%Y-W%W"))  # weekly horizon
            self._events(self.wifi.scan())
            self._spawn_ble()
            meters = self.gps.distance()
            if meters > 0:
                self._progress(mechanics.walk(self.state, meters, self.cfg))
                self._forage(meters)
                self._quest("distance_m", meters)
                self.wallet.earn(shop_mod.scrap_for_walk(meters))
                self._achievements()
        except Exception as e:  # noqa: BLE001 - never break the tick loop
            self.log(f"tick step failed: {e}")
        mechanics.tick(self.state, dt * self.cfg.time_scale, self.cfg)
        self._starve_warn_check()
        if mechanics.is_dead(self.state):
            self._hardcore_death()
        try:
            self._home_check()
            # occasional mood-driven chatter when nothing else is happening
            now = time.time()
            if now - self._last_idle > 20:
                m = mechanics.mood(self.state)
                if m in ("hungry", "sick", "tired", "happy", "sleeping"):
                    self.speak(m)
                self._last_idle = now
        except Exception as e:  # noqa: BLE001 - never break the tick loop
            self.log(f"tick idle step failed: {e}")

    # how many ticks between repeat STARVING warnings within the same stage
    _STARVE_WARN_EVERY = 6

    def _starve_warn_check(self) -> None:
        """Hardcore ONLY: shout an escalating warning while the pet is in a severe
        starvation stage, BEFORE it can die. Throttled -- fires on every stage
        transition and then only once every _STARVE_WARN_EVERY ticks, so it never
        spams the log on a long downhill slide."""
        if not getattr(self.state, "hardcore", False):
            return
        stage = mechanics.starvation_stage(self.state)
        if stage not in ("starving", "faint"):
            self._starve_warn = ("", self._tick_i)
            return
        last_stage, last_tick = self._starve_warn
        transitioned = stage != last_stage
        if not transitioned and (self._tick_i - last_tick) < self._STARVE_WARN_EVERY:
            return
        self._starve_warn = (stage, self._tick_i)
        urgency = "ABOUT TO DIE" if stage == "faint" else "STARVING"
        self.log(f"[HARDCORE] {self.state.name} is {urgency} -- "
                 f"feed it or it dies!")
        self._fx_set("sick")

    def _hardcore_death(self) -> None:
        """Hardcore mode: the pet starved to death. It is reborn as a fresh egg,
        keeping only its name + the locked-in hardcore mode; all progress resets.
        The bestiary/inventory/wallet (your collection) are left intact."""
        old = self.state
        self.log(f"[HARDCORE] {old.name} starved to death at Lv{old.level} "
                 f"({old.stage}). Reborn as an egg -- keep it fed this time!")
        self._fx_set("sick")
        self.state = mechanics.reborn(old)
        self._save()

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
        self.larder.save()
        self.book.save()
        self.trackers.save()
        self.ledger.save()
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
