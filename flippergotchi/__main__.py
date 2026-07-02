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


def _prompt_name(cfg) -> str:
    """Name a brand-new pet. Tty-guarded: in --simulate or with no TTY it uses
    the default ("Flippy") so automation/sim never blocks on input()."""
    default = getattr(cfg, "name", "Flippy") or "Flippy"
    if getattr(cfg, "simulate", False) or not sys.stdin.isatty():
        return default
    try:
        ans = input(f"  Name your new pet [{default}] > ").strip()
    except (EOFError, KeyboardInterrupt):
        return default
    return ans or default


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
    # The CLI runs the autonomous pet/scanner loop; `doctor` is a hardware
    # preflight diagnostic. All GAMEPLAY actions (dex, battle, duel, shop, feed,
    # gear, quests, achievements, title, profile, scan, capture, cloud) are
    # driven from the on-device UI (button navigation) -- they are not CLI
    # subcommands. The implementations live in flippergotchi/commands.py as the
    # UI action layer.
    ap.add_argument("command", nargs="?", default="run",
                    choices=["run", "doctor"],
                    help="run (the pet/scanner loop, default) | "
                         "doctor (hardware/tooling preflight)")
    args = ap.parse_args()

    cfg = Config.load(args.config)
    # Resolve all state paths to concrete locations under state_dir. This makes
    # `~` HOME-unset-safe (systemd) and moves every default path together when
    # state_dir is overridden. Test suites build Config() directly and never hit
    # this, so their explicit tmp paths are unaffected.
    cfg.apply_state_dir()
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

    if args.command == "doctor":
        from .commands import cmd_doctor
        cmd_doctor(cfg)
        return

    # a pet is "born" on --reset or the very first run (no save yet); that's the
    # only time the mode can be chosen, and it's then locked into the save.
    fresh = args.reset or not os.path.exists(os.path.expanduser(cfg.state_path))
    cfg.fresh_pet = fresh   # let the Agent show the one-time hatch/onboarding
    if fresh:
        state = PetState()
        state.hardcore = _choose_hardcore(args.hardcore, cfg)
        if state.hardcore:
            print("** HARDCORE mode: keep it fed -- starvation is permanent. **")
        # name the newborn (tty-guarded; --name still wins below)
        if not args.name:
            state.name = _prompt_name(cfg)
    else:
        state = persistence.load(cfg.state_path)
        if args.hardcore and not state.hardcore:
            print("(--hardcore ignored: mode is locked for an existing pet)")
    if args.name or not state.name:
        state.name = cfg.name

    Agent(cfg, state).run(ticks=args.ticks)


if __name__ == "__main__":
    main()
