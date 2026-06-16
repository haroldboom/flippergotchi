"""`dex`, `battle`, `encounter` subcommands."""
from __future__ import annotations

from . import prefs as prefs_mod
from .game import battle as battle_mod
from .game import encounter as enc_mod
from .game import monsters
from .game.bestiary import Bestiary
from .game.home import WARNING
from .game.ledger import Ledger
from .game.monsters import label
from .view import animations

_ICON = {"cracked": "WIN", "tamed": "TAMED", "failed": "LOSS",
         "refused": "BLOCKED", "immune": "IMMUNE", "submitted": "ESCALATED"}


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


def _fight(m, cfg, authorized: bool, ledger: Ledger) -> str:
    res = battle_mod.battle(m, cfg, force_authorized=authorized)
    m.attempts += 1
    m.last_result = res["result"]
    cat = ledger.record(m, res["result"], res.get("via", ""), res.get("key", ""))
    icon = _ICON.get(res["result"], res["result"].upper())
    extra = (f" -- key: {res['key']}" if res.get("key") else "")
    note = (f"\n    note: {res['note']}" if res.get("note") else "")
    print(f"  [{icon}] {label(m):<22} {res['result']} via {res['via']}{extra}{note}")
    return cat or ""


def cmd_battle(cfg, target: str | None, authorized: bool,
               all_: bool = False, dont_show: bool = False) -> None:
    dex = Bestiary(cfg.bestiary_path)
    ledger = Ledger(cfg.ledger_path)
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
            _fight(m, cfg, authorized, ledger)
        ledger.save()
        dex.save()
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
    _fight(m, cfg, authorized, ledger)
    ledger.save()
    dex.save()
