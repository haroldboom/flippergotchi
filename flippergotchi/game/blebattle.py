"""Befriending BLE signal-sprites: the Bluetooth analog of catching a WiFi
monster, played out as a short little courtship rather than a single roll.

A signal-sprite is a shy roaming critter made of stray Bluetooth chirps. You
don't hack it -- you win it over, one gentle step at a time. The shyer its
temperament (its pairing security), the more coaxing it takes:

  LISTEN   catch its roaming chirps + trail on the air
  GREET    coax a fresh hello out of a coy sprite so it turns to look at you
  HUM      hum its little tune back until it warms up (open sprites hum along
           instantly; coy ones make you try a few notes)
  EASE     for a bashful sprite, patiently ease its jittery guard down so it
           lets you close (rare -- most bashful sprites stay standoffish)
  BOOP     a gentle boop hello -- win it over by playing, no coaxing needed
           (jingle a bell, kindle a glow)

Befriending a sprite earns you its **song-signature** (a keepsake of its tune)
plus a little whimsical trinket as loot. The real BLE hooks under the hood use
``crackle`` / ``bleak`` (guarded, sim-safe, NEEDS ON-HARDWARE VALIDATION).
``battle_ble`` returns a battle()-style dict with extra ``steps`` (the courtship
log, for the render) and ``loot``.
"""
from __future__ import annotations

import logging
import os
import random
import shutil
import subprocess

log = logging.getLogger(__name__)

# species -> a friendly little "play" gesture: (label, characteristic-uuid, value).
# The uuid/value are the real (guarded) GATT hooks; only the label is flavour.
_CONTROL = {
    "Trackling": ("jingle its bell", "00002a06-0000-1000-8000-00805f9b34fb", b"\x02"),
    "Hearthkin": ("kindle its glow", "", b"\x01"),
    "Echobub": ("hum a duet", "", b"\x7f"),
    "Blip": ("boop the beacon", "", b"\x01"),
    "Vitalix": ("match its pulse", "", b"\x01"),
    "Cogling": ("wind it up", "", b"\x01"),
}
_DEFAULT_CONTROL = ("give it a boop", "", b"\x01")

# species -> the whimsical trinket you're gifted when a sprite befriends you.
_LOOT = {
    "Trackling": "a wandering spark", "Echobub": "a looping echo",
    "Hearthkin": "a warm ember", "Vitalix": "a steady pulse-mote",
    "Keytapper": "a flurry of taps", "Pocketling": "a pocket-glimmer",
    "Cogling": "a clockwork cog", "Blip": "a blinking bauble",
    "Tickbit": "a bouncy step-spark", "Pixie": "a fistful of static",
}

_KNOB_CHANCE = 0.35        # odds a bashful sprite lets its guard down (secure target)


def control_move(monster):
    return _CONTROL.get(getattr(monster, "species", ""), _DEFAULT_CONTROL)


def _fake_ltk() -> str:
    return "".join(random.choice("0123456789abcdef") for _ in range(32))


def battle_ble(monster, cfg) -> dict:
    """Befriend a BLE signal-sprite as a little courtship sequence. Sets
    monster.defeated/key when it warms up to you. Returns a battle()-style dict
    with ``steps`` (the courtship log) + ``loot``."""
    pairing = getattr(monster, "pairing", "just_works") or "just_works"
    connectable = bool(getattr(monster, "connectable", True))
    loot = _LOOT.get(getattr(monster, "species", ""), "a fistful of static")
    steps = [("LISTEN", "caught its roaming chirps + trail")]

    # --dry-run must NEVER transmit -- exercise the courtship narration but skip
    # the real crackle/GATT-write hops (mirrors the WiFi native/bettercap paths
    # and LocalCracker._crack_dry). Without this, `battle <ble> --dry-run` would
    # actually connect + write_gatt_char on real hardware.
    if bool(getattr(cfg, "dry_run", False)) and not bool(getattr(cfg, "simulate", False)):
        steps.append(("DRY-RUN", "would befriend it here -- no signal sent"))
        return {"result": "dry-run", "via": "dry-run", "key": "", "mode": pairing,
                "note": "dry-run: no active BLE performed", "loot": None, "steps": steps}

    if pairing in ("just_works", "pin"):
        if pairing == "pin":
            steps.append(("GREET", "coaxed a fresh hello"))
        steps.append(("HUM", "hummed its open lullaby" if pairing == "just_works"
                      else "hummed through its shy little tune"))
        res = _do_crack(monster, cfg, pairing, via="crackle")
    else:                                   # bashful sprite (LE Secure Connections)
        if _downgrade(cfg):
            steps.append(("EASE", "eased its jittery guard down"))
            steps.append(("ATTUNE", "matched its shy rhythm"))
            res = _do_crack(monster, cfg, "secure", via="knob+crackle")
        elif connectable:
            steps.append(("EASE", "couldn't ease its guard"))
            label = control_move(monster)[0]
            steps.append(("BOOP", label))
            res = _do_control(monster, cfg)
        else:
            steps.append(("EASE", "couldn't ease its guard"))
            res = {"result": "immune", "via": "-", "key": "", "mode": "secure",
                   "note": "too bashful and won't come near -- can't befriend yet"}

    if res["result"] == "cracked":
        monster.defeated = True
        monster.key = res["key"]
        res["loot"] = loot
        steps.append(("FRIEND", f"{res.get('note', '')} +{loot}"))
    elif res["result"] == "immune":
        steps.append(("BASHFUL", "stayed shy"))
    else:
        steps.append(("SKITTISH", res.get("note", "")))
    res["steps"] = steps
    return res


def _downgrade(cfg) -> bool:
    """Whether a bashful sprite lets its guard down. Sim: a roll. Real: not
    implemented (this is the hard path), so bashful sprites fall back to a
    friendly boop or stay shy on real hardware."""
    if not bool(getattr(cfg, "simulate", False)):
        return False
    return random.random() < _KNOB_CHANCE


# -- hum its tune until it warms up (crackle under the hood) ----------------
def _do_crack(monster, cfg, pairing: str, via: str) -> dict:
    if not bool(getattr(cfg, "simulate", False)):
        real = _crackle(monster, cfg)
        if real is not None:
            return real
    p = {"just_works": 0.95, "pin": 0.65, "secure": 0.9}.get(pairing, 0.8)
    if random.random() < p:
        return {"result": "cracked", "via": f"{via} (sim)", "key": _fake_ltk(),
                "mode": pairing, "note": f"learned its little song ({pairing})"}
    return {"result": "failed", "via": f"{via} (sim)", "key": "", "mode": pairing,
            "note": "it darted off before we could hum along"}


def _crackle(monster, cfg):
    """Real crackle on a sniffed pairing pcap. NEEDS ON-HARDWARE VALIDATION."""
    crackle = shutil.which(getattr(cfg, "crackle_bin", "crackle"))
    cap = getattr(monster, "capture_path", "") or ""
    if not crackle or not cap or not os.path.exists(cap):
        return None
    try:
        out = subprocess.run([crackle, "-i", cap], capture_output=True,
                             text=True, timeout=120)
    except Exception:  # noqa: BLE001
        return None
    ltk = _parse_ltk(out.stdout or "")
    if ltk:
        return {"result": "cracked", "via": "crackle", "key": ltk,
                "mode": "pairing", "note": "learned its whole song"}
    return {"result": "failed", "via": "crackle", "key": "",
            "mode": "pairing", "note": "couldn't catch its tune (too shy?)"}


def _parse_ltk(text: str) -> str:
    for line in text.splitlines():
        low = line.lower()
        if "ltk" in low and ":" in line:
            return line.split(":")[-1].strip().replace(" ", "")
    return ""


# -- win it over with a friendly boop (GATT write under the hood) -----------
def _do_control(monster, cfg) -> dict:
    action = control_move(monster)[0]
    if not bool(getattr(cfg, "simulate", False)):
        real = _gatt_write(monster, cfg)
        if real is not None:
            return real
    if random.random() < 0.7:
        return {"result": "cracked", "via": "gatt-write", "mode": "control",
                "key": f"(friend: {action})", "note": f"won it over -- {action}"}
    return {"result": "failed", "via": "gatt-write", "mode": "control",
            "key": "", "note": f"couldn't {action}"}


def _gatt_write(monster, cfg):
    """bleak GATT write to the sprite's play characteristic. NEEDS
    ON-HARDWARE VALIDATION."""
    action, uuid, value = control_move(monster)
    if not uuid:
        return None
    try:
        import asyncio
        from bleak import BleakClient  # type: ignore
    except Exception:
        return None

    async def _go():
        async with BleakClient(str(monster.id),
                               timeout=getattr(cfg, "ble_tame_timeout", 8.0)) as c:
            await c.write_gatt_char(uuid, value, response=False)
            return True

    try:
        asyncio.run(_go())
        return {"result": "cracked", "via": "gatt-write", "mode": "control",
                "key": f"(friend: {action})", "note": f"won it over -- {action}"}
    except Exception as exc:  # noqa: BLE001
        log.warning("gatt play gesture failed (%s)", exc)
        return {"result": "failed", "via": "gatt-write", "mode": "control",
                "key": "", "note": f"couldn't {action}"}
