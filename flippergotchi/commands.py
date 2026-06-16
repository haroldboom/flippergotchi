"""`dex` and `battle` subcommands - inspect your collection and fight monsters."""
from __future__ import annotations

from .game import battle as battle_mod
from .game.bestiary import Bestiary


def cmd_dex(cfg) -> None:
    dex = Bestiary(cfg.bestiary_path)
    rows = dex.all()
    if not rows:
        print("Your bestiary is empty. Go for a walk and catch some monsters!")
        return
    print(f"  BESTIARY  ({len(rows)} discovered)")
    print(f"  {'lvl':>3}  {'species':<12} {'name':<20} {'type':<6} "
          f"{'def':>3}  status")
    for m in rows:
        if m.defeated:
            status = f"DEFEATED (key: {m.key})" if m.key else "tamed"
        elif m.captured:
            status = "captured - ready to battle"
        else:
            status = "spotted (not captured)"
        print(f"  {m.level:>3}  {m.species:<12} {m.name[:20]:<20} {m.kind:<6} "
              f"{m.defense:>3}  {status}")


def cmd_battle(cfg, target: str, authorized: bool) -> None:
    dex = Bestiary(cfg.bestiary_path)
    m = dex.get(target)
    if not m:
        print(f"No monster matching '{target}' in your bestiary. Try `dex`.")
        return
    print(f"Engaging {m.species} '{m.name}' (Lv{m.level}, {m.encryption or m.kind}, "
          f"defense {m.defense})...")
    res = battle_mod.battle(m, cfg, force_authorized=authorized)
    icon = {"cracked": "WIN", "tamed": "TAMED", "failed": "LOSS",
            "refused": "BLOCKED", "immune": "IMMUNE",
            "submitted": "UPLOADED"}.get(res["result"], res["result"].upper())
    print(f"[{icon}] {res['result']} via {res['via']}"
          + (f" -- key: {res['key']}" if res.get("key") else "")
          + (f"\n  note: {res['note']}" if res.get("note") else ""))
    dex.save()
