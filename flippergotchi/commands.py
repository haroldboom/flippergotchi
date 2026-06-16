"""`dex`, `battle`, `encounter` subcommands."""
from __future__ import annotations

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
from .game.ledger import Ledger
from .game.monsters import label
from .game.quests import QuestLog
from .pet import mechanics
from .pet.state import PetState
from .view import animations

import time


def _today() -> str:
    return time.strftime("%Y-%m-%d")

_ICON = {"cracked": "WIN", "tamed": "TAMED", "failed": "LOSS",
         "refused": "BLOCKED", "submitted": "ESCALATED"}


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
    print("\n  > you chose: CAPTURE\n")
    e.choose("capture", rng=_AlwaysHit)
    for frame in animations.frames(e.animation, m):
        print(frame)
        print()
    print(f"  => {e.message}")


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
                           element=getattr(state, "element", "Aether"))
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
        loot = equip_mod.roll_item(boost=peer["level"])
        inv.add(loot)
        print(f"  you seized {loot.rarity} gear: {loot.name} (+{loot.power} pow)")
        quests = QuestLog(cfg.quests_path)
        quests.roll(_today())
        for q in quests.record("duel_wins", 1):
            rw = quests_mod.grant_quest_reward(q, state, inv, cfg)
            print(f"  [quest] {q.description} done -> {rw}")
        quests.save()
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


def cmd_quests(cfg) -> None:
    """Show today's daily quests and progress."""
    q = QuestLog(cfg.quests_path)
    q.roll(_today())
    rows = q.active()
    if not rows:
        print("No quests today. Go for a walk to roll some!")
        return
    print(f"  DAILY QUESTS ({q.day})")
    for quest in rows:
        pct = min(100, int(quest.progress / quest.target * 100)) if quest.target else 100
        bar = "#" * (pct // 10) + "." * (10 - pct // 10)
        mark = "DONE" if quest.done else f"{bar} {quest.progress:g}/{quest.target:g}"
        reward = ", ".join(f"{k}:{v}" for k, v in (quest.reward or {}).items())
        print(f"  [{'x' if quest.done else ' '}] {quest.description:<22} {mark}"
              f"   -> {reward}")
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


def _fight(m, cfg, authorized: bool, ledger: Ledger, inv=None, state=None,
           quests=None) -> str:
    res = battle_mod.battle(m, cfg, force_authorized=authorized)
    m.attempts += 1
    m.last_result = res["result"]
    cat = ledger.record(m, res["result"], res.get("via", ""), res.get("key", ""))
    icon = _ICON.get(res["result"], res["result"].upper())
    extra = (f" -- key: {res['key']}" if res.get("key") else "")
    note = (f"\n    note: {res['note']}" if res.get("note") else "")
    print(f"  [{icon}] {label(m):<22} {res['result']} via {res['via']}{extra}{note}")
    # defeating a monster is the reward loop: loot + a treat for the pet + quests
    if res["result"] == "cracked":
        if inv is not None:
            loot = inv.add(equip_mod.roll_item(boost=m.level // 2))
            print(f"      loot: {loot.rarity} {loot.name} (+{loot.power} pow)")
        if state is not None:
            mechanics.snack(state, cfg)  # a treat for cracking it
        if quests is not None and state is not None:
            for q in quests.record("cracks", 1):
                rw = quests_mod.grant_quest_reward(q, state, inv, cfg)
                print(f"      [quest] {q.description} done -> {rw}")
    return cat or ""


def cmd_battle(cfg, target: str | None, authorized: bool,
               all_: bool = False, dont_show: bool = False) -> None:
    dex = Bestiary(cfg.bestiary_path)
    ledger = Ledger(cfg.ledger_path)
    inv = equip_mod.Inventory(cfg.inventory_path)
    state = persistence.load(cfg.state_path)
    quests = QuestLog(cfg.quests_path)
    quests.roll(_today())
    _show_warning(cfg, dont_show)

    if all_:
        # Auto-battle every captured, not-yet-defeated WiFi monster, one at a
        # time. Keys are unique BSSIDs already; dedupe defensively anyway.
        seen, queue = set(), []
        for m in dex.all():
            if m.kind == "wifi" and m.captured and not m.defeated and m.id not in seen:
                seen.add(m.id)
                queue.append(m)
        if not queue:
            print("Nothing to auto-battle (no captured, un-defeated WiFi monsters).")
            return
        print(f"Auto-battling {len(queue)} unique target(s)...\n")
        for m in queue:
            _fight(m, cfg, authorized, ledger, inv, state, quests)
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
        print("Usage: battle <name|bssid> [--authorized]  |  battle --all")
        return
    m = dex.get(target)
    if not m:
        print(f"No monster matching '{target}' in your bestiary. Try `dex`.")
        return
    print(f"Engaging {m.species} '{label(m)}' (Lv{m.level}, "
          f"{m.encryption or m.kind}, defense {m.defense})...")
    _fight(m, cfg, authorized, ledger, inv, state, quests)
    ledger.save()
    dex.save()
    inv.save()
    quests.save()
    persistence.save(cfg.state_path, state)
