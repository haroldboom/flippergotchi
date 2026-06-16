from __future__ import annotations

import random


class BluetoothScanner:
    """Source of Bluetooth/BLE devices -> small monsters.

    mode="sim"  -> emits fake BLE devices for development
    mode="live" -> TODO: BlueZ via `bluetoothctl`/bleak; classic BT inquiry +
                   BLE advertising scan -> {type, addr, name, appearance, rssi}.
    """

    def __init__(self, cfg):
        self.cfg = cfg
        self.mode = "sim" if cfg.simulate else "live"

    def poll(self) -> list:
        if self.mode != "sim":
            return []  # TODO: live BlueZ scan (devices + Flippergotchi peers)
        # occasionally another Flippergotchi is nearby (advertises name + stats)
        if random.random() < 0.05:
            return [{
                "type": "peer",
                "addr": ":".join("%02X" % random.randint(0, 255) for _ in range(6)),
                "name": random.choice(["Sparkfin", "RogueDolphin", "ByteSurf",
                                       "NixWave", "GotchiX"]),
                "level": random.randint(1, 14),
                "handshakes": random.randint(0, 40),
                "gear_power": random.randint(0, 35),
            }]
        if random.random() < 0.15:
            appearance = random.choice(
                ["phone", "wearable", "audio", "beacon", "computer", "unknown"])
            return [{
                "type": "ble",
                "addr": ":".join("%02X" % random.randint(0, 255) for _ in range(6)),
                "name": random.choice(
                    ["Galaxy Buds", "Mi Band", "JBL Flip", "Tile", "iPhone",
                     "(unnamed)", "Fitbit", "AirPods"]),
                "appearance": appearance,
                "rssi": random.randint(-95, -45),
            }]
        return []
