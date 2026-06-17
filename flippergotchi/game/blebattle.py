"""BLE battling: the Bluetooth analog of cracking a WiFi handshake.

Two ways to "defeat" (own) a BLE monster, by its pairing security:

  * **LE Legacy Pairing** (Just Works / 6-digit PIN) -> crack the Temporary Key
    -> STK -> LTK with **crackle** (the BLE aircrack). With the LTK you can
    decrypt the device's traffic. Trivial for Just Works, fast for PIN.
  * **LE Secure Connections** (ECDH) -> can't crack; but if the device is
    connectable you can still take **control** by writing to an unauthenticated
    GATT characteristic (ring a tracker, toggle a bulb, …). Only a secure +
    non-connectable device is a true immune boss.

Real paths use ``crackle`` (needs a sniffed pairing capture, e.g. Ubertooth /
Sniffle) and ``bleak`` GATT writes -- both guarded, sim-safe, and marked
NEEDS ON-HARDWARE VALIDATION. The result dict matches ``battle()``'s contract.
"""
from __future__ import annotations

import logging
import os
import random
import shutil
import subprocess

log = logging.getLogger(__name__)

# species -> a benign GATT "control" move: (label, characteristic-uuid, value).
# An empty uuid means there's no known characteristic, so the real write can't
# run (sim still flavours it). NEEDS ON-HARDWARE VALIDATION.
_CONTROL = {
    # Immediate Alert service -> Alert Level char: 0x02 = "high" -> tag plays a sound
    "Trackling": ("ring it", "00002a06-0000-1000-8000-00805f9b34fb", b"\x02"),
    "Hearthkin": ("toggle power", "", b"\x01"),
    "Echobub": ("blast the volume", "", b"\x7f"),
    "Blip": ("hijack the beacon", "", b"\x01"),
    "Vitalix": ("spoof a reading", "", b"\x01"),
    "Cogling": ("poke it", "", b"\x01"),
}
_DEFAULT_CONTROL = ("poke it", "", b"\x01")


def control_move(monster):
    return _CONTROL.get(getattr(monster, "species", ""), _DEFAULT_CONTROL)


def _fake_ltk() -> str:
    return "".join(random.choice("0123456789abcdef") for _ in range(32))


def battle_ble(monster, cfg) -> dict:
    """Battle a BLE monster: crack its pairing, or take control. Sets
    monster.defeated/key on a win. Returns a battle()-style result dict."""
    pairing = getattr(monster, "pairing", "just_works") or "just_works"
    connectable = bool(getattr(monster, "connectable", True))

    if pairing in ("just_works", "pin"):
        res = _crack_pairing(monster, cfg, pairing)
    elif connectable:
        res = _control(monster, cfg)            # secure pairing -> try control
    else:
        return {"result": "immune", "via": "-", "key": "", "mode": "secure",
                "note": "LE Secure Connections + not connectable -- can't be owned"}

    if res["result"] == "cracked":
        monster.defeated = True
        monster.key = res["key"]
    return res


# -- pairing crack (crackle) ------------------------------------------------
def _crack_pairing(monster, cfg, pairing: str) -> dict:
    if not bool(getattr(cfg, "simulate", False)):
        real = _crackle(monster, cfg)
        if real is not None:
            return real
    # sim: Just Works almost always lands; PIN usually does.
    p = 0.95 if pairing == "just_works" else 0.65
    if random.random() < p:
        return {"result": "cracked", "via": "crackle (sim)", "key": _fake_ltk(),
                "mode": pairing, "note": f"LTK recovered from {pairing} pairing"}
    return {"result": "failed", "via": "crackle (sim)", "key": "",
            "mode": pairing, "note": "no pairing captured / TK not found"}


def _crackle(monster, cfg):
    """Real crackle on a sniffed pairing pcap. NEEDS ON-HARDWARE VALIDATION."""
    crackle = shutil.which(getattr(cfg, "crackle_bin", "crackle"))
    cap = getattr(monster, "capture_path", "") or ""
    if not crackle or not cap or not os.path.exists(cap):
        return None
    try:
        out = subprocess.run([crackle, "-i", cap], capture_output=True,
                             text=True, timeout=120)
    except Exception:  # noqa: BLE001 - never raise out of a crack
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
def _control(monster, cfg) -> dict:
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
        return None                              # no known char -> sim flavour
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
