from __future__ import annotations

import random


class BettercapClient:
    """Source of WiFi capture events (the pet's food supply).

    mode="sim"  -> emits fake handshake/PMKID events for development
    mode="live" -> TODO: drive a real bettercap session over its REST + websocket
                   API against the MT7921 monitor interface.
    """

    def __init__(self, cfg):
        self.cfg = cfg
        self.mode = "sim" if cfg.simulate else "live"

    def start(self):
        if self.mode == "live":
            # TODO: POST to {cfg.bettercap_url}/api/session to run:
            #   set wifi.interface <iface>; wifi.recon on; wifi.recon.channel <hop>
            # then open the events websocket and translate:
            #   wifi.client.handshake -> {"type":"handshake","kind":"handshake"|"pmkid"}
            #   wifi.ap.new           -> {"type":"ap", ...}
            raise NotImplementedError(
                "live bettercap backend not wired yet - run with --simulate"
            )

    def poll(self) -> list:
        if self.mode == "sim":
            return self._sim_poll()
        return []

    def _sim_poll(self) -> list:
        events = []
        if random.random() < 0.4:
            events.append({"type": "ap", **_rand_ap()})
        r = random.random()
        if r < 0.18:
            events.append({"type": "handshake", "kind": "handshake", **_rand_ap()})
        elif r < 0.30:
            events.append({"type": "handshake", "kind": "pmkid", **_rand_ap()})
        return events


def _rand_ap() -> dict:
    return {
        "bssid": _rand_bssid(),
        "ssid": _rand_ssid(),
        "encryption": random.choice(
            ["wpa2", "wpa2", "wpa2", "wpa", "open", "wep", "wpa3", "wpa2-eap"]),
        "band": random.choice(["2.4GHz", "2.4GHz", "5GHz", "6GHz"]),
        "wps": random.random() < 0.3,
        "clients": random.randint(0, 4),
        "signal": random.randint(-85, -40),
    }


def _rand_bssid() -> str:
    return ":".join("%02X" % random.randint(0, 255) for _ in range(6))


_SSIDS = ["Linksys", "NETGEAR", "TP-LINK_2G", "xfinitywifi", "HomeNet",
          "FBI_Surveillance_Van", "Pretty_Fly_for_WiFi", "Telstra1234",
          "iiNet_5G", "OPTUS_A1B2"]


def _rand_ssid() -> str:
    return random.choice(_SSIDS)
