"""Reward cadence: sim spawn rates are throttled so encounters feel earned.

Gameplay tuning quick-win #1 ("throttle the firehose"): in --simulate the
AP/BLE sim polls used to fire on ~35%/~15% of ticks. These tests pin the
new, lower rates via named constants and verify the observed emit rate.
"""
from __future__ import annotations

import random

from flippergotchi.config import Config
from flippergotchi.core import bluetooth
from flippergotchi.core.bettercap import SIM_AP_SPAWN_CHANCE, BettercapClient
from flippergotchi.core.bluetooth import SIM_BLE_SPAWN_CHANCE, BluetoothScanner


def _sim_cfg():
    cfg = Config()
    cfg.simulate = True
    return cfg


# -- constants --------------------------------------------------------------
def test_sim_spawn_constants_are_throttled():
    assert SIM_AP_SPAWN_CHANCE == 0.12
    assert SIM_BLE_SPAWN_CHANCE == 0.05
    # Sanity: materially lower than the old firehose rates (0.35 / 0.15).
    assert SIM_AP_SPAWN_CHANCE <= 0.35 / 2
    assert SIM_BLE_SPAWN_CHANCE <= 0.15 / 2


def test_sim_poll_uses_the_constants():
    # The poll paths must reference the module constants (tunable in one
    # place), not a re-hardcoded literal.
    import inspect
    assert "SIM_AP_SPAWN_CHANCE" in inspect.getsource(BettercapClient._sim_poll)
    assert "SIM_BLE_SPAWN_CHANCE" in inspect.getsource(BluetoothScanner.poll)


# -- observed cadence -------------------------------------------------------
def test_ap_sim_emit_rate_matches_constant():
    client = BettercapClient(_sim_cfg())
    assert client.mode == "sim"
    random.seed(1234)
    n = 5000
    hits = sum(1 for _ in range(n) if client._sim_poll())
    rate = hits / n
    # Statistically around the tuned value, and well below the old 0.35.
    assert abs(rate - SIM_AP_SPAWN_CHANCE) < 0.03
    assert rate < 0.20


def test_ble_sim_emit_rate_is_throttled():
    scanner = BluetoothScanner(_sim_cfg())
    assert scanner.mode == "sim"
    random.seed(1234)
    n = 5000
    generic = 0
    total_emitting = 0
    for _ in range(n):
        out = scanner.poll()
        if out:
            total_emitting += 1
            ev = out[0]
            is_stalker = ev.get("addr") == bluetooth._STALKER_ADDR
            if ev.get("type") != "peer" and not is_stalker:
                generic += 1
    # Generic-device branch fires ~SIM_BLE_SPAWN_CHANCE of remaining polls
    # (after the rarer peer/stalker branches), i.e. well below the old 0.15.
    generic_rate = generic / n
    assert abs(generic_rate - SIM_BLE_SPAWN_CHANCE) < 0.02
    assert generic_rate < 0.10
    # Even counting peers/stalkers, overall BLE cadence stays modest.
    assert total_emitting / n < 0.20
