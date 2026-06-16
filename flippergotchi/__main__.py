from __future__ import annotations

import argparse

from . import persistence
from .agent import Agent
from .config import Config
from .pet.state import PetState


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="flippergotchi",
        description="A Tamagotchi-style WiFi pet for the Flipper One.",
    )
    ap.add_argument("-c", "--config", help="path to a config.toml (py3.11+)")
    ap.add_argument("--simulate", action="store_true",
                    help="fake wifi/gps events - dev without hardware")
    ap.add_argument("--name", help="override pet name")
    ap.add_argument("--ticks", type=int, default=None,
                    help="run N ticks then exit (default: run forever)")
    ap.add_argument("--interval", type=float, help="seconds per tick")
    ap.add_argument("--time-scale", type=float,
                    help="multiply time decay (handy with --simulate)")
    ap.add_argument("--plain", action="store_true",
                    help="log events only; no full-screen face")
    ap.add_argument("--reset", action="store_true", help="start a brand new pet")
    # RPG subcommands (default is to just run the pet/scanner loop)
    ap.add_argument("command", nargs="?", default="run",
                    choices=["run", "dex", "battle", "encounter"],
                    help="run (default) | dex | battle <name> | encounter (demo)")
    ap.add_argument("target", nargs="?", help="monster name/bssid for `battle`")
    ap.add_argument("--authorized", action="store_true",
                    help="confirm you're cleared to crack this target (battle)")
    ap.add_argument("--all", dest="all", action="store_true",
                    help="battle: auto-battle every captured monster, one at a time")
    ap.add_argument("--dont-show-again", dest="dont_show_again", action="store_true",
                    help="battle: dismiss the crack warning permanently")
    args = ap.parse_args()

    cfg = Config.load(args.config)
    if args.simulate:
        cfg.simulate = True
    if args.name:
        cfg.name = args.name
    if args.interval is not None:
        cfg.tick_interval = args.interval
    if args.time_scale is not None:
        cfg.time_scale = args.time_scale
    if args.plain:
        cfg.tui = False

    if args.command == "dex":
        from .commands import cmd_dex
        cmd_dex(cfg)
        return
    if args.command == "encounter":
        from .commands import cmd_encounter
        cmd_encounter(cfg)
        return
    if args.command == "battle":
        if not args.target and not args.all:
            ap.error("battle needs a monster name/bssid (e.g. `battle Linksys`) "
                     "or --all")
        from .commands import cmd_battle
        cmd_battle(cfg, args.target, args.authorized, args.all, args.dont_show_again)
        return

    state = PetState() if args.reset else persistence.load(cfg.state_path)
    if args.name or not state.name:
        state.name = cfg.name

    Agent(cfg, state).run(ticks=args.ticks)


if __name__ == "__main__":
    main()
