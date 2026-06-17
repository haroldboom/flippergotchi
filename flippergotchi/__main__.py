from __future__ import annotations

import argparse
import os
import sys

from . import persistence
from .agent import Agent
from .config import Config
from .pet.state import PetState


def _choose_hardcore(flag: bool, cfg) -> bool:
    """Pick the mode for a brand-new pet. `--hardcore` forces it on; otherwise a
    one-time on-screen prompt (skipped in --simulate or when there is no TTY, so
    automation/sim default to Normal). The choice is LOCKED for the pet's life."""
    if flag:
        return True
    if getattr(cfg, "simulate", False) or not sys.stdin.isatty():
        return False
    print("New pet! Pick a mode -- this is LOCKED for its whole life:")
    print("  [N] Normal   -- your pet can't die; hunger is gentle, food optional")
    print("  [H] Hardcore -- starvation is PERMADEATH (reborn as an egg); feed it!")
    try:
        return input("  mode [N/h] > ").strip().lower().startswith("h")
    except (EOFError, KeyboardInterrupt):
        return False


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="flippergotchi",
        description="A Tamagotchi-style WiFi pet for the Flipper One.",
    )
    ap.add_argument("-c", "--config", help="path to a config.toml (py3.11+)")
    ap.add_argument("--simulate", action="store_true",
                    help="fake wifi/gps events - dev without hardware")
    ap.add_argument("--dry-run", dest="dry_run", action="store_true",
                    help="drive real capture/crack paths but suppress deauth "
                         "injection + hashcat (validate the stack on hardware)")
    ap.add_argument("--capture-timeout", dest="capture_timeout", type=int,
                    help="seconds to listen for a handshake per capture attempt")
    ap.add_argument("--name", help="override pet name")
    ap.add_argument("--ticks", type=int, default=None,
                    help="run N ticks then exit (default: run forever)")
    ap.add_argument("--interval", type=float, help="seconds per tick")
    ap.add_argument("--time-scale", type=float,
                    help="multiply time decay (handy with --simulate)")
    ap.add_argument("--plain", action="store_true",
                    help="log events only; no full-screen face")
    ap.add_argument("--manual", action="store_true",
                    help="prompt [A]Capture / [B]Run on each encounter")
    ap.add_argument("--variant", choices=["classic", "hammerhead", "goblin", "sawshark", "whaleshark"],
                    help="shark species variant")
    ap.add_argument("--reset", action="store_true", help="start a brand new pet")
    ap.add_argument("--hardcore", action="store_true",
                    help="start a HARDCORE pet: starvation is permadeath "
                         "(new pet only; the mode is locked for its life)")
    # RPG subcommands (default is to just run the pet/scanner loop)
    ap.add_argument("command", nargs="?", default="run",
                    choices=["run", "dex", "battle", "encounter", "duel", "gear",
                             "quests", "doctor", "shop", "achievements", "scan",
                             "capture", "cloud", "feed", "title", "profile"],
                    help="run | dex | battle <name> | encounter | duel <peer> | "
                         "gear [item] | quests | doctor | shop [buy <item>] | "
                         "achievements | scan | capture <bssid> | "
                         "cloud [submit <name>|results] | feed [food-id] | "
                         "title [name|none] | profile")
    ap.add_argument("target", nargs="?", help="monster name/bssid for `battle`; "
                    "bssid/ssid for `capture`; or `buy`/item-id for `shop`")
    ap.add_argument("extra", nargs="?", help="item id for `shop buy <item>`")
    ap.add_argument("--authorized", action="store_true",
                    help="confirm you're cleared to crack this target (battle)")
    ap.add_argument("--all", dest="all", action="store_true",
                    help="battle: auto-battle every captured monster, one at a time")
    ap.add_argument("--dont-show-again", dest="dont_show_again", action="store_true",
                    help="battle: dismiss the crack warning permanently")
    ap.add_argument("--stash", dest="stash", action="store_true",
                    help="shop: deposit a bought feed item into the larder "
                         "instead of instant-feeding (hunger unchanged)")
    args = ap.parse_args()

    cfg = Config.load(args.config)
    if args.simulate:
        cfg.simulate = True
    if args.dry_run:
        cfg.dry_run = True
    if args.capture_timeout is not None:
        cfg.capture_timeout = args.capture_timeout
    if args.name:
        cfg.name = args.name
    if args.interval is not None:
        cfg.tick_interval = args.interval
    if args.time_scale is not None:
        cfg.time_scale = args.time_scale
    if args.plain:
        cfg.tui = False
    if args.manual:
        cfg.manual = True
    if args.variant:
        cfg.character_variant = args.variant

    if args.command == "dex":
        from .commands import cmd_dex
        cmd_dex(cfg)
        return
    if args.command == "encounter":
        from .commands import cmd_encounter
        cmd_encounter(cfg)
        return
    if args.command == "duel":
        from .commands import cmd_duel
        cmd_duel(cfg, args.target)
        return
    if args.command == "gear":
        from .commands import cmd_gear
        cmd_gear(cfg, args.target)
        return
    if args.command == "quests":
        from .commands import cmd_quests
        cmd_quests(cfg)
        return
    if args.command == "doctor":
        from .commands import cmd_doctor
        cmd_doctor(cfg)
        return
    if args.command == "shop":
        from .commands import cmd_shop
        cmd_shop(cfg, args.target, args.extra, stash=args.stash)
        return
    if args.command == "achievements":
        from .commands import cmd_achievements
        cmd_achievements(cfg)
        return
    if args.command == "feed":
        from .commands import cmd_feed
        cmd_feed(cfg, args.target)
        return
    if args.command == "title":
        from .commands import cmd_title
        cmd_title(cfg, args.target)
        return
    if args.command == "profile":
        from .commands import cmd_profile
        cmd_profile(cfg)
        return
    if args.command == "scan":
        from .commands import cmd_scan
        cmd_scan(cfg)
        return
    if args.command == "capture":
        from .commands import cmd_capture
        cmd_capture(cfg, args.target, args.authorized)
        return
    if args.command == "cloud":
        from .commands import cmd_cloud
        cmd_cloud(cfg, args.target, args.extra, args.authorized)
        return
    if args.command == "battle":
        # no target + no --all  ->  open the Battle Dojo menu (auto/manual)
        from .commands import cmd_battle
        cmd_battle(cfg, args.target, args.authorized, args.all, args.dont_show_again)
        return

    # a pet is "born" on --reset or the very first run (no save yet); that's the
    # only time the mode can be chosen, and it's then locked into the save.
    fresh = args.reset or not os.path.exists(os.path.expanduser(cfg.state_path))
    if fresh:
        state = PetState()
        state.hardcore = _choose_hardcore(args.hardcore, cfg)
        if state.hardcore:
            print("** HARDCORE mode: keep it fed -- starvation is permanent. **")
    else:
        state = persistence.load(cfg.state_path)
        if args.hardcore and not state.hardcore:
            print("(--hardcore ignored: mode is locked for an existing pet)")
    if args.name or not state.name:
        state.name = cfg.name

    Agent(cfg, state).run(ticks=args.ticks)


if __name__ == "__main__":
    main()
