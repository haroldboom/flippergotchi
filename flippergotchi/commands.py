"""`dex`, `battle`, `encounter` subcommands."""
from __future__ import annotations

import os

from . import persistence
from . import prefs as prefs_mod
from .game import battle as battle_mod
from .game import duel as duel_mod
from .game import encounter as enc_mod
from .game import equipment as equip_mod
from .game import monsters
from .game.bestiary import Bestiary
from .game.home import WARNING
from .game import quests as quests_mod
from .game import shop as shop_mod
from .game import food as food_mod
from .game import achievements as ach_mod
from .game.larder import Larder
from .game.achievements import AchievementBook
from .game.ledger import Ledger
from .game.monsters import label
from .game.quests import QuestLog
from .game.shop import Wallet
from .pet import mechanics
from .pet.state import PetState
from .view import animations

import time


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def _thisweek() -> str:
    return time.strftime("%Y-W%W")


def _quest_bonus(cfg, quests) -> None:
    """Pay the all-dailies-clear bonus once per day from the CLI side."""
    bonus = quests.claim_daily_bonus(_today())
    if bonus:
        quests_mod._credit_scrap(cfg, None, bonus)
        print(f"  [quest] all dailies cleared! +{bonus} scrap bonus")

_ICON = {"cracked": "WIN", "tamed": "TAMED", "failed": "LOSS",
         "refused": "BLOCKED", "submitted": "ESCALATED", "dry-run": "DRY-RUN"}


def cmd_dex(cfg) -> None:
    dex = Bestiary(cfg.bestiary_path)
    rows = dex.all()
    if not rows:
        print("Your bestiary is empty. Go for a walk and catch some monsters!")
        return
    c = Ledger(cfg.ledger_path).counts()
    print(f"  BESTIARY  ({len(rows)} unique BSSIDs)   "
          f"record: {c['win']}W / {c['loss']}L / {c['escalate']} escalated")
    print(f"  {'lvl':>3}  {'species':<12} {'name':<22} {'type':<6} "
          f"{'def':>3}  status")
    for m in rows:
        if m.defeated:
            status = f"DEFEATED (key: {m.key})" if m.key else "tamed"
        elif m.captured:
            status = "captured - ready to battle"
        else:
            status = "spotted (not captured)"
        print(f"  {m.level:>3}  {m.species:<12} {label(m)[:22]:<22} {m.kind:<6} "
              f"{m.defense:>3}  {status}")


class _AlwaysHit:
    @staticmethod
    def random():
        return 0.0  # deterministic catch, so the demo shows the net animation


def cmd_encounter(cfg) -> None:
    """Demo one encounter end-to-end (popup -> animation -> outcome)."""
    ev = {"type": "ap", "ssid": "DemoNet", "bssid": "AA:BB:CC:11:22:33",
          "encryption": "wpa2", "band": "5GHz", "clients": 3, "signal": -52}
    m = monsters.from_ap(ev)
    e = enc_mod.Encounter(m)
    print(animations.popup(m))
    # render the visual 256x144 "A wild <species> appeared!" card
    out = _render_encounter(cfg, m)
    if out:
        print(f"  [screen] encounter -> {out}")
    print("\n  > you chose: CAPTURE\n")
    e.choose("capture", rng=_AlwaysHit)
    for frame in animations.frames(e.animation, m):
        print(frame)
        print()
    # render the visual net-gun capture frames (the device swaps through these)
    caught = e.state == enc_mod.CAUGHT
    frames = _render_capture(cfg, m, caught)
    if frames:
        print(f"  [screen] capture animation -> {os.path.dirname(frames[0])} "
              f"({len(frames)} frames)")
    print(f"  => {e.message}")


def _player_stem(cfg) -> str:
    variant = getattr(cfg, "character_variant", "classic")
    return "adult" if variant in ("classic", "") else f"{variant}-adult"


def _render_capture(cfg, m, caught: bool) -> list | None:
    """Best-effort visual net-gun capture frames; never breaks the flow.

    The status HUD reflects the live deauth/capture settings (cfg.deauth_count,
    cfg.capture_timeout) -- the same values the real capture uses."""
    try:
        from .view import capture_screen
        out = getattr(cfg, "capture_frames_dir", "/tmp/flippergotchi/capture")
        return capture_screen.render_sequence(
            os.path.expanduser(out),
            {"species": m.species, "name": label(m)},
            caught=caught, player=_player_stem(cfg),
            timeout=int(getattr(cfg, "capture_timeout", 20) or 20),
            deauth=int(getattr(cfg, "deauth_count", 5) or 5))
    except Exception:  # noqa: BLE001
        return None


def _render_encounter(cfg, m, line: str = "") -> str | None:
    """Best-effort visual encounter card; never breaks the encounter flow."""
    try:
        from .view import encounter_screen
        out = getattr(cfg, "encounter_html_out", "/tmp/flippergotchi/encounter.html")
        return encounter_screen.render(os.path.expanduser(out), {
            "species": m.species, "name": label(m), "level": m.level,
            "encryption": m.encryption, "defense": m.defense, "kind": m.kind,
        }, line)
    except Exception:  # noqa: BLE001
        return None


def cmd_duel(cfg, target: str | None) -> None:
    """Challenge another Flippergotchi (detected over BLE) to a PvP duel."""
    state = persistence.load(cfg.state_path)
    peers = prefs_mod.load(cfg.peers_path)

    if not target:
        if not peers:
            print("No Flippergotchi peers detected yet. Walk near another one "
                  "(it advertises over Bluetooth), then `duel <name>`.")
            return
        print("Nearby Flippergotchis:")
        for p in peers.values():
            print(f"  {p['name']:<14} Lv{p['level']:<3} {p['handshakes']} handshakes")
        print("\nChallenge one with:  duel <name>")
        return

    peer = next((p for p in peers.values()
                 if p["name"].lower() == target.lower() or p["addr"] == target), None)
    if not peer:
        print(f"No peer named '{target}' nearby. Try `duel` to list them.")
        return

    inv = equip_mod.Inventory(cfg.inventory_path)
    you = duel_mod.Fighter(name=state.name, level=state.level,
                           handshakes=state.handshakes, health=state.health,
                           happiness=state.happiness, gear=inv.gear_power(),
                           element=getattr(state, "element", "Aether"),
                           satiety=getattr(state, "satiety", 0.0))
    them = duel_mod.Fighter(name=peer["name"], level=peer["level"],
                            handshakes=peer["handshakes"],
                            gear=peer.get("gear_power", 0),
                            element=peer.get("element", "Aether"), addr=peer["addr"])
    print(f"== DIGI-DUEL ==  {you.name} vs {them.name}\n")
    res = duel_mod.duel(you, them, cfg)
    for line in res.log:
        print(f"  {line}")
    duel_mod.apply_result(state, res)

    # ...and the loser forfeits a bit of gear
    if res.you_won:
        state.duel_wins = getattr(state, "duel_wins", 0) + 1
        loot = equip_mod.roll_item(boost=peer["level"])
        inv.add(loot)
        print(f"  you seized {loot.rarity} gear: {loot.name} (+{loot.power} pow)")
        quests = QuestLog(cfg.quests_path)
        quests.roll(_today())
        quests.roll_weekly(_thisweek())
        for q in quests.record("duel_wins", 1):
            rw = quests_mod.grant_quest_reward(q, state, inv, cfg)
            print(f"  [quest] {q.description} done -> {rw}")
        _quest_bonus(cfg, quests)
        quests.save()
        _award(cfg, state, scrap=shop_mod.scrap_for_duel_win(), inv=inv,
               quests=quests)
    else:
        forfeit = inv.pick_forfeit()
        if forfeit:
            inv.remove(forfeit.id)
            print(f"  {them.name} stripped your {forfeit.name} (-{forfeit.power} pow)")
        else:
            print("  you had no gear to forfeit.")
    inv.save()
    persistence.save(cfg.state_path, state)
    verb = "won" if res.you_won else "lost"
    print(f"\n  You {verb}. Handshake pool: {state.handshakes}  |  "
          f"gear power: {inv.gear_power()}")
    # render the 1v1 battle screen
    from .view import battle_screen
    variant = getattr(cfg, "character_variant", "classic")
    me_sprite = state.stage if variant in ("classic", "") else f"{variant}-{state.stage}"
    out = battle_screen.render(
        os.path.expanduser(cfg.battle_html_out),
        {"name": state.name, "level": state.level,
         "health": 100 if res.you_won else 30, "sprite": me_sprite},
        {"name": them.name, "level": them.level,
         "health": 30 if res.you_won else 100, "sprite": "blue-adult"},
        res.log[-1] if res.log else f"{res.winner} wins!")
    print(f"  [screen] battle -> {out}")


def cmd_quests(cfg) -> None:
    """Show today's daily + this week's weekly quests and progress (read-only)."""
    q = QuestLog(cfg.quests_path)
    q.roll(_today())
    q.roll_weekly(_thisweek())
    if not q.active() and not q.active_weeklies():
        print("No quests today. Go for a walk to roll some!")
        return

    def _show(quest):
        pct = min(100, int(quest.progress / quest.target * 100)) if quest.target else 100
        bar = "#" * (pct // 10) + "." * (10 - pct // 10)
        mark = "DONE" if quest.done else f"{bar} {quest.progress:g}/{quest.target:g}"
        reward = ", ".join(f"{k}:{v}" for k, v in (quest.reward or {}).items())
        print(f"  [{'x' if quest.done else ' '}] {quest.description:<26} {mark}"
              f"   -> {reward}")

    streak = f"   streak: {q.streak}d" if q.streak else ""
    print(f"  DAILY QUESTS ({q.day})   completed lifetime: {q.lifetime_done}{streak}")
    for quest in q.active():
        _show(quest)
    if q.all_dailies_done():
        state = "claimed" if q.bonus_day == q.day else "ready -- finishes on next action"
        print(f"  >> all dailies clear!  +{quests_mod.DAILY_CLEAR_BONUS} scrap bonus ({state})")
    if q.active_weeklies():
        print(f"  WEEKLY QUESTS ({q.week})")
        for quest in q.active_weeklies():
            _show(quest)
    q.save()


def cmd_gear(cfg, target: str | None) -> None:
    """List your inventory, or toggle equip/unequip for an item by id/name."""
    inv = equip_mod.Inventory(cfg.inventory_path)
    if target:
        it = inv.items.get(target) or next(
            (x for x in inv.items.values() if x.name.lower() == target.lower()), None)
        if not it:
            print(f"No gear matching '{target}'. Run `gear` to list.")
            return
        if inv.is_equipped(it.id):
            inv.unequip_slot(it.slot)
            print(f"Unequipped {it.name}.")
        else:
            inv.equip(it.id)
            print(f"Equipped {it.name} in [{it.slot}].")
        inv.save()
        return
    # equipment screen: a row per slot (equipped item or empty) + the loot bag
    print(f"  EQUIPMENT   PvP gear power: {inv.gear_power()}  "
          f"(boosts duels only -- gear can't crack WiFi)")
    for slot in equip_mod.SLOTS:
        iid = inv.equipped.get(slot)
        it = inv.items.get(iid) if iid else None
        if it:
            print(f"  {slot:<9}: {it.name:<22} {it.rarity:<9} "
                  f"+{it.bonus_val:g} {it.bonus_stat.upper()}")
        else:
            print(f"  {slot:<9}: (empty)")
    bag = [it for it in inv.all() if not inv.is_equipped(it.id)]
    if bag:
        print(f"\n  BAG ({len(bag)}) -- `gear <id>` to equip/unequip:")
        for it in bag:
            print(f"    [{it.slot:<8}] {it.name:<22} {it.rarity:<9} "
                  f"+{it.bonus_val:g} {it.bonus_stat.upper()}   {it.id}")
    # render the visual equipment screen (character wearing the gear)
    from .view import equip_screen
    state = persistence.load(cfg.state_path)
    variant = getattr(cfg, "character_variant", "classic")
    sprite = state.stage if variant in ("classic", "") else f"{variant}-{state.stage}"
    out = equip_screen.render(os.path.expanduser(cfg.equip_html_out), inv, sprite)
    print(f"\n  [screen] equipment view -> {out}")


def _show_warning(cfg, dont_show: bool) -> None:
    """Print the crack warning unless the user has dismissed it for good."""
    prefs = prefs_mod.load(cfg.prefs_path)
    if prefs.get("hide_battle_warning"):
        return
    print(WARNING)
    if dont_show:
        prefs["hide_battle_warning"] = True
        prefs_mod.save(cfg.prefs_path, prefs)
        print("  [x] do not show again  (saved - won't warn next time)\n")
    else:
        print("  [ ] do not show again  (pass --dont-show-again to tick this)\n")


def _award(cfg, state, *, scrap: int = 0, inv=None, dex=None, ledger=None,
           quests=None) -> None:
    """Earn `scrap` for an action and unlock any newly-met achievements (printing
    + saving the wallet/book). The caller still owns saving state/inv/dex/ledger.

    Uses the LIVE in-memory inv/dex/ledger so milestones reflect this action
    without needing a reload, and routes the badge rewards through the single
    achievements.grant_reward path. Never raises out of the reward loop."""
    try:
        wallet = Wallet(getattr(cfg, "wallet_path", "~/.flippergotchi/wallet.json"))
        if scrap:
            wallet.earn(scrap)
            print(f"      +{scrap} scrap  (balance: {wallet.scrap})")
        dex = dex or Bestiary(cfg.bestiary_path)
        ledger = ledger or Ledger(cfg.ledger_path)
        inv = inv or equip_mod.Inventory(cfg.inventory_path)
        book = AchievementBook(getattr(cfg, "achievements_path",
                                       "~/.flippergotchi/achievements.json"))
        qlog = quests if quests is not None else QuestLog(cfg.quests_path)
        stats = ach_mod.build_stats(state, dex, inv, ledger, qlog)
        for b in ach_mod.grant_reward(book, stats, state, cfg, wallet, inv):
            rw = b.reward or {}
            bits = []
            if rw.get("scrap"):
                bits.append(f"+{rw['scrap']} scrap")
            if rw.get("gear"):
                bits.append("gear")
            extra = f"  ({', '.join(bits)})" if bits else ""
            print(f"      ★ ACHIEVEMENT: {b.name} -- {b.description}{extra}")
        wallet.save()
        book.save()
    except Exception as e:  # noqa: BLE001 - rewards must never break a battle/duel
        print(f"      [award skipped: {e}]")


def _fight(m, cfg, authorized: bool, ledger: Ledger, inv=None, state=None,
           quests=None, dex=None) -> str:
    res = battle_mod.battle(m, cfg, force_authorized=authorized)
    m.attempts += 1
    m.last_result = res["result"]
    cat = ledger.record(m, res["result"], res.get("via", ""), res.get("key", ""))
    icon = _ICON.get(res["result"], res["result"].upper())
    extra = (f" -- key: {res['key']}" if res.get("key") else "")
    note = (f"\n    note: {res['note']}" if res.get("note") else "")
    print(f"  [{icon}] {label(m):<22} {res['result']} via {res['via']}{extra}{note}")
    if m.kind == "ble":
        try:
            from .view import blebattle_screen
            outdir = os.path.expanduser(getattr(cfg, "blebattle_frames_dir",
                                                "/tmp/flippergotchi/blebattle"))
            player = _player_stem(cfg)
            if state is not None:
                variant = getattr(cfg, "character_variant", "classic")
                player = (state.stage if variant in ("classic", "")
                          else f"{variant}-{state.stage}")
            frames = blebattle_screen.render_sequence(
                outdir, {"species": m.species, "name": label(m),
                         "level": m.level, "pairing": getattr(m, "pairing", "")},
                res, player=player)
            steps = " → ".join(s[0] for s in res.get("steps", []))
            print(f"      techniques: {steps}")
            if res.get("loot"):
                print(f"      intel: {res['loot']}")
            print(f"      [screen] ble battle -> {outdir} ({len(frames)} frames)")
        except Exception:  # noqa: BLE001
            pass
    # defeating a monster is the reward loop: loot + a treat for the pet + quests
    if res["result"] == "cracked":
        if inv is not None:
            loot = inv.add(equip_mod.roll_item(boost=m.level // 2))
            print(f"      loot: {loot.rarity} {loot.name} (+{loot.power} pow)")
        if state is not None:
            mechanics.snack(state, cfg)  # a treat for cracking it
        if quests is not None and state is not None:
            done = list(quests.record("cracks", 1))
            if getattr(m, "rarity", "") == "legendary":
                done += list(quests.record("legendary_kills", 1))
            for q in done:
                rw = quests_mod.grant_quest_reward(q, state, inv, cfg)
                print(f"      [quest] {q.description} done -> {rw}")
            _quest_bonus(cfg, quests)
        if state is not None and dex is not None:
            _award(cfg, state, scrap=shop_mod.scrap_for_crack(),
                   inv=inv, dex=dex, ledger=ledger, quests=quests)
    return cat or ""


def _ready_targets(dex) -> list:
    """Captured monsters (WiFi + BLE) you HAVEN'T battled yet -- the AUTO/MANUAL
    pool. BLE monsters are battled by cracking their pairing / taking control."""
    seen, out = set(), []
    for m in dex.all():
        if (m.kind in ("wifi", "ble") and m.captured and not m.defeated
                and m.attempts == 0 and m.id not in seen):
            seen.add(m.id)
            out.append(m)
    return out


def _render_dojo(cfg, dex, ledger, state) -> None:
    """The home Battle Dojo section: render the menu + target list and print
    the same info + button map for the terminal."""
    ready = _ready_targets(dex)
    cracked = sum(1 for m in dex.all() if m.kind in ("wifi", "ble") and m.defeated)
    variant = getattr(cfg, "character_variant", "classic")
    player = state.stage if variant in ("classic", "") else f"{variant}-{state.stage}"
    from .view import battle_menu
    items = [{"name": label(m), "level": m.level,
              # WiFi shows its encryption; BLE shows its pairing security
              "encryption": m.encryption if m.kind == "wifi"
              else getattr(m, "pairing", ""),
              "rarity": m.rarity, "kind": m.kind} for m in ready]
    try:
        mo = battle_menu.render_menu(os.path.expanduser(cfg.battlemenu_html_out),
                                     len(ready), cracked, player=player)
        lo = battle_menu.render_list(os.path.expanduser(cfg.battlelist_html_out),
                                     items)
        print(f"  [screen] battle menu -> {mo}")
        print(f"  [screen] target list -> {lo}")
    except Exception as e:  # noqa: BLE001
        print(f"  [screen] (render skipped: {e})")

    print(f"\n  == BATTLE DOJO ==   {len(ready)} ready · {cracked} cracked")
    print("  [A] AUTO BATTLE  — crack every fresh target  (`battle --all`)")
    print("  [B] MANUAL       — pick one below            (`battle <name>`)")
    if items:
        print("\n  targets you haven't battled yet:")
        for it in items[:12]:
            tag = (it["rarity"] or it["encryption"] or "").upper()
            print(f"    · {it['name']:<22} Lv{it['level']:<3} {tag}")
        if len(items) > 12:
            print(f"    … +{len(items) - 12} more")
    else:
        print("\n  No fresh targets — go catch some monsters first!")
    b = battle_menu.BUTTONS  # device button map
    print(f"\n  device: {b['open']} opens · {b['up']}/{b['down']} move · "
          f"{b['select']} select · {b['back']} exit")


def cmd_battle(cfg, target: str | None, authorized: bool,
               all_: bool = False, dont_show: bool = False) -> None:
    dex = Bestiary(cfg.bestiary_path)
    ledger = Ledger(cfg.ledger_path)
    inv = equip_mod.Inventory(cfg.inventory_path)
    state = persistence.load(cfg.state_path)
    quests = QuestLog(cfg.quests_path)
    quests.roll(_today())
    quests.roll_weekly(_thisweek())
    _show_warning(cfg, dont_show)

    if all_:
        # AUTO BATTLE: every captured WiFi target you HAVEN'T battled yet
        # (attempts == 0), one at a time. Unique BSSIDs; dedupe defensively.
        queue = _ready_targets(dex)
        if not queue:
            print("Nothing to auto-battle (no fresh captured targets).")
            return
        print(f"Auto-battling {len(queue)} unique target(s)...\n")
        for m in queue:
            _fight(m, cfg, authorized, ledger, inv, state, quests, dex)
        ledger.save()
        dex.save()
        inv.save()
        quests.save()
        persistence.save(cfg.state_path, state)
        c = ledger.counts()
        print(f"\nLifetime record: {c['win']} wins / {c['loss']} losses / "
              f"{c['escalate']} escalated to cloud")
        return

    if not target:
        _render_dojo(cfg, dex, ledger, state)
        return
    m = dex.get(target)
    if not m:
        print(f"No monster matching '{target}' in your bestiary. Try `dex`.")
        return
    print(f"Engaging {m.species} '{label(m)}' (Lv{m.level}, "
          f"{m.encryption or m.kind}, defense {m.defense})...")
    _fight(m, cfg, authorized, ledger, inv, state, quests, dex)
    ledger.save()
    dex.save()
    inv.save()
    quests.save()
    persistence.save(cfg.state_path, state)


def cmd_doctor(cfg) -> None:
    """Preflight: what's installed/permitted for real WiFi capture + cracking."""
    from .game import doctor
    doctor.run(cfg)


def cmd_achievements(cfg) -> None:
    """Show unlocked + locked badges and your scrap balance.

    READ-ONLY: badges are earned (and paid out) through play, via the single
    achievements.grant_reward path fired on real progress events -- viewing the
    list never unlocks or pays anything, so it can't be used to farm scrap."""
    book = AchievementBook(getattr(cfg, "achievements_path",
                                   "~/.flippergotchi/achievements.json"))
    wallet = Wallet(getattr(cfg, "wallet_path", "~/.flippergotchi/wallet.json"))
    # read-only progress snapshot (no unlock, no grant) for the locked-badge bars
    state = persistence.load(cfg.state_path)
    dex = Bestiary(cfg.bestiary_path)
    inv = equip_mod.Inventory(cfg.inventory_path)
    ledger = Ledger(cfg.ledger_path)
    stats = ach_mod.build_stats(state, dex, inv, ledger, QuestLog(cfg.quests_path))

    unlocked = book.unlocked()
    print(f"  ACHIEVEMENTS  ({len(unlocked)}/{len(book.all())})   "
          f"scrap: {wallet.scrap}")
    if getattr(state, "active_title", ""):
        earned = len(getattr(state, "titles", []))
        suffix = f"   ({earned} titles earned)" if earned > 1 else ""
        print(f"  Title: {state.name} {state.active_title}{suffix}")
    _TIER = {"bronze": "B", "silver": "S", "gold": "G", "": "-"}
    last_cat = None
    for b in book.all():
        got = book.is_unlocked(b.id)
        if b.category != last_cat:
            print(f"  -- {b.category} --")
            last_cat = b.category
        mark = "★" if got else " "
        name = ach_mod.display_name(b, got)
        line = f"  [{mark}] ({_TIER.get(b.tier, '-')}) {name:<22}"
        if got:
            line += f" {b.description}"
        elif b.hidden:
            line += " (secret -- keep playing)"
        else:
            cur, thr = ach_mod.progress(b, stats)
            line += f" {b.description}  [{int(cur)}/{int(thr)}]"
        print(line)


def cmd_feed(cfg, target: str | None = None) -> None:
    """`feed` shows the larder + pet; `feed <id>` hand-feeds that stashed food.

    Foraging stashes food in the larder while the pet isn't hungry; this is the
    player-driven verb that spends it. Renders the feeding screen."""
    state = persistence.load(cfg.state_path)
    larder = Larder(getattr(cfg, "larder_path", "~/.flippergotchi/larder.json"),
                    getattr(cfg, "larder_capacity", 20))
    eaten, msg = None, ""
    if target:
        fk = food_mod.get(target)
        if fk is None:
            msg = f"no such food '{target}'  (try: feed)"
        elif not larder.take(fk.id):
            msg = f"no {fk.name} in the larder"
        else:
            mechanics.snack(state, cfg, fk)
            eaten = fk.id
            larder.save()
            persistence.save(cfg.state_path, state)
            msg = f"fed {fk.name}  (+{int(fk.restore)} food)"

    try:
        from .view import feed_screen
        out = getattr(cfg, "feed_html_out", "/tmp/flippergotchi/feed.html")
        feed_screen.render(out, state, cfg, larder, eaten=eaten)
        print(f"  [screen] feed -> {out}")
    except Exception as e:  # noqa: BLE001 - render must never break the command
        print(f"  [feed render failed: {e}]")

    food_pct = int(max(0, min(100, 100 - state.hunger)))
    print(f"  LARDER  ({larder.total()}/{larder.capacity})   food: {food_pct}%")
    counts = larder.counts()
    for fk in food_mod.all_kinds():
        n = counts.get(fk.id, 0)
        if n:
            mark = "*" if eaten == fk.id else " "
            print(f"  [{mark}] {fk.id:<8} x{n:<2} {fk.name} (+{int(fk.restore)} food)")
    if not counts:
        print("  (larder empty -- walk to forage food)")
    if msg:
        print(f"  -> {msg}")


def cmd_shop(cfg, action: str | None, item: str | None) -> None:
    """`shop` to browse; `shop buy <item>` to spend scrap."""
    shop = shop_mod.Shop(cfg)
    wallet = Wallet(getattr(cfg, "wallet_path", "~/.flippergotchi/wallet.json"))

    # support both `shop buy <item>` and `shop <item>`
    if action and action != "buy":
        item = item or action
        action = "buy"

    if action == "buy":
        if not item:
            print("Usage: shop buy <item-id>")
            return
        state = persistence.load(cfg.state_path)
        inv = equip_mod.Inventory(cfg.inventory_path)
        ok, msg = shop.buy(wallet, item, inv=inv, state=state)
        print(f"  {msg}")
        if ok:
            wallet.save()
            inv.save()
            persistence.save(cfg.state_path, state)
        return

    print(f"  SHOP   (scrap: {wallet.scrap})   buy with `shop buy <id>`")
    for it in shop.list_items():
        afford = "  " if wallet.can_afford(it.cost) else " x"
        print(f"  [{afford}] {it.id:<14} {it.cost:>4} scrap   {it.name} -- "
              f"{it.description}")


def _make_backend(cfg):
    """Build the capture backend + the authorizer that gates its active actions
    (imported lazily so non-WiFi commands stay cheap)."""
    from .core.authz import Authorizer
    from .core.wifi.backends import make_backend
    authz = Authorizer(cfg)
    return make_backend(cfg, is_authorized=authz.is_authorized), authz


def cmd_scan(cfg, rounds: int = 8) -> None:
    """Passive AP discovery via the selected capture backend.

    Read-only: no deauth, no injection -- safe to run on real hardware to
    validate monitor mode + scanning (see `doctor` for prerequisites). In sim
    it shows synthesised APs."""
    backend, _ = _make_backend(cfg)
    tag = " (dry-run)" if getattr(cfg, "dry_run", False) else ""
    print(f"  SCAN  backend={type(backend).__name__}{tag}  -- passive, no "
          f"active actions")
    try:
        backend.start()
    except Exception as e:  # noqa: BLE001
        print(f"  backend start failed: {e}")
    found: dict = {}
    try:
        for _ in range(max(1, int(rounds))):
            for ap in backend.scan() or []:
                b = ap.get("bssid")
                if b:
                    found[b] = ap
    except Exception as e:  # noqa: BLE001
        print(f"  scan error: {e}")
    finally:
        try:
            backend.stop()
        except Exception:  # noqa: BLE001
            pass
    if not found:
        print("  no APs discovered. On hardware run `doctor` to confirm a "
              "monitor-capable interface + tools; in sim it's random per tick.")
        return
    print(f"  {len(found)} AP(s) seen:")
    print(f"  {'bssid':<18} {'enc':<5} {'band':<6} {'sig':>4} {'cl':>3}  ssid")
    for ap in sorted(found.values(), key=lambda a: a.get("signal", -99),
                     reverse=True):
        print(f"  {str(ap.get('bssid','')):<18} {str(ap.get('encryption','')):<5} "
              f"{str(ap.get('band','')):<6} {int(ap.get('signal',0) or 0):>4} "
              f"{int(ap.get('clients',0) or 0):>3}  {ap.get('ssid','')}")


def cmd_capture(cfg, target: str | None, authorized: bool = False) -> None:
    """Attempt a single handshake/PMKID capture and validate the result.

    Honors --dry-run (never transmits -- passive listen only, logs what it
    WOULD deauth) and the authorization scope (active deauth only against your
    dojo). The capture file, if any, is validated by core.handshake."""
    if not target:
        print("Usage: capture <bssid|ssid>  [--dry-run] [--authorized]")
        return
    from .core import handshake as hs
    backend, authz = _make_backend(cfg)
    bssid, ssid = target, ""
    dry = bool(getattr(cfg, "dry_run", False))
    in_scope = authorized or authz.is_authorized(bssid, ssid)
    if dry:
        mode = "DRY-RUN (passive; would-deauth logged, none sent)"
    elif in_scope:
        mode = "ACTIVE (authorized -> deauth nudge allowed)"
    else:
        mode = "PASSIVE (out of scope -> no deauth)"
    # audit the intent either way (allowed/denied is recorded in the log)
    authz.require("capture", bssid, ssid)
    print(f"  CAPTURE {bssid}  backend={type(backend).__name__}  mode={mode}")
    try:
        backend.start()
        path = backend.capture_handshake(
            bssid, ssid, timeout=getattr(cfg, "capture_timeout", 20))
    except Exception as e:  # noqa: BLE001
        print(f"  capture failed: {e}")
        path = None
    finally:
        try:
            backend.stop()
        except Exception:  # noqa: BLE001
            pass
    if not path:
        print("  no capture produced (expected in sim / without a monitor radio "
              "in range of the target).")
        return
    info = hs.analyze_capture(path)
    print(f"  capture file: {path}")
    print(f"  valid={bool(info)}  pmkid={info.contains_pmkid}  "
          f"eapol_msgs={sorted(info.eapol_messages)}  "
          f"complete_4way={info.has_complete_4way}")
    if bool(info):
        nextstep = ("crack it with `battle <name> --authorized`"
                    if not dry else
                    "re-run without --dry-run (and --authorized) to crack it")
        print(f"  -> crackable. {nextstep}")
    else:
        print("  -> not yet crackable (need a PMKID or a complete 4-way).")


def cmd_cloud(cfg, action: str | None, target: str | None,
              authorized: bool = False) -> None:
    """Distributed cloud cracking via wpa-sec/onlinehashcrack.

      cloud                 -- status (service, key set?, queued captures)
      cloud submit <name|capture-file>   -- upload a captured handshake
      cloud results         -- fetch recovered PSKs and apply them to the dex

    Uploading a capture is outward-facing: it's gated to your scope (or
    --authorized), honors --dry-run, and only runs when cloud_enabled."""
    from .game.cracking import CloudCracker
    service = getattr(cfg, "cloud_service", "wpa-sec")
    enabled = bool(getattr(cfg, "cloud_enabled", False))

    if not action:
        key_set = bool(getattr(cfg, "wpa_sec_key", "")
                       or getattr(cfg, "onlinehashcrack_key", ""))
        print(f"  CLOUD  service={service}  enabled={enabled}  key_set={key_set}")
        dex = Bestiary(cfg.bestiary_path)
        pend = [m for m in dex.all()
                if m.kind == "wifi" and m.captured and not m.defeated]
        print(f"  {len(pend)} captured WiFi monster(s) not yet cracked. Upload one"
              " with `cloud submit <name>`, then `cloud results`.")
        if not enabled:
            print("  note: set cloud_enabled = true to allow uploads.")
        return

    if action == "results":
        results = CloudCracker(cfg).fetch_results()
        if not results:
            print("  no recovered keys available (nothing cracked yet, or no "
                  "wpa_sec_key / not in live mode).")
            return
        dex = Bestiary(cfg.bestiary_path)
        ledger = Ledger(cfg.ledger_path)
        applied = 0
        for m in dex.all():
            if m.kind == "wifi" and not m.defeated and m.id.upper() in results:
                m.defeated = True
                m.key = results[m.id.upper()]
                m.last_result = "cracked"
                ledger.record(m, "cracked", "cloud", m.key)
                print(f"  [WIN] {label(m):<22} cracked via cloud -- key: {m.key}")
                applied += 1
        dex.save()
        ledger.save()
        print(f"  applied {applied} recovered key(s) of {len(results)} known to "
              f"{service}.")
        return

    if action == "submit":
        if not enabled:
            print("  cloud uploads are disabled. Set cloud_enabled = true first.")
            return
        if not target:
            print("Usage: cloud submit <monster-name|bssid|capture-file>")
            return
        dex = Bestiary(cfg.bestiary_path)
        # resolve the monster + capture file from a name/bssid or a raw path
        m = dex.get(target)
        if m is None and os.path.exists(target):
            m = next((x for x in dex.all()
                      if getattr(x, "capture_path", "") == target), None)
        path = (target if os.path.exists(target)
                else (getattr(m, "capture_path", "") if m else ""))
        if not path:
            print(f"  no capture file for '{target}'. Pass a .pcap path, or a "
                  "monster whose capture_path is set.")
            return
        # scope gate (uploading someone's handshake to a 3rd party)
        from .core.authz import Authorizer
        authz = Authorizer(cfg)
        in_scope = authorized or (m is not None and authz.is_authorized(m.id, m.name))
        if not in_scope and not getattr(cfg, "dry_run", False):
            print("  refused: target not in your authorized scope. Re-run with "
                  "--authorized if you own/are cleared to test it.")
            authz.require("crack", getattr(m, "id", target), getattr(m, "name", ""))
            return
        authz.require("crack", getattr(m, "id", target), getattr(m, "name", ""))
        res = CloudCracker(cfg).submit(m, path).to_dict()
        icon = _ICON.get(res["result"], res["result"].upper())
        print(f"  [{icon}] {os.path.basename(path)} -> {res['result']} via "
              f"{res['via']}: {res.get('note', '')}")
        if res["result"] == "submitted" and m is not None:
            Ledger(cfg.ledger_path).record(m, "submitted", res["via"])
            m.last_result = "submitted"
            dex.save()
        return

    print(f"Unknown cloud action '{action}'. Use: submit | results")
