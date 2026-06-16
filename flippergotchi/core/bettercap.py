from __future__ import annotations

import base64
import json
import logging
import random
import urllib.error
import urllib.request

log = logging.getLogger(__name__)


class BettercapClient:
    """Source of WiFi capture events (the pet's food supply).

    mode="sim"  -> emits fake handshake/PMKID events for development
    mode="live" -> drive a real bettercap session over its REST API against
                   the monitor interface (e.g. MT7921 mon0).

    LIVE PREREQUISITES (needs validation on real hardware):
      * bettercap must be running with the REST API enabled, e.g.
            bettercap -iface <iface> -eval "set api.rest.username user; \
                set api.rest.password pass; api.rest on"
        listening on cfg.bettercap_url (default http://127.0.0.1:8081).
      * HTTP basic-auth credentials come from cfg.bettercap_user /
        cfg.bettercap_pass (defaults "user"/"pass" via getattr).
    """

    def __init__(self, cfg):
        self.cfg = cfg
        self.mode = "sim" if cfg.simulate else "live"
        # When the live backend can't be reached we degrade to a no-op poll()
        # instead of crashing the agent. Set in start() on failure.
        self._degraded = False
        # Highest bettercap event timestamp we've already emitted, so each
        # poll() only translates *new* events. ISO-8601 strings sort
        # lexicographically, so a plain string compare is sufficient.
        self._last_ts = ""
        # Basic-auth header, lazily built in start().
        self._auth_header = ""

    # -- live REST helpers ------------------------------------------------
    def _url(self, path: str) -> str:
        base = str(getattr(self.cfg, "bettercap_url", "http://127.0.0.1:8081"))
        return base.rstrip("/") + path

    def _request(self, path: str, payload=None, timeout: float = 5.0):
        """Issue an authenticated GET/POST and return the decoded JSON body.

        POST when ``payload`` is given, GET otherwise. Raises on any
        network/HTTP error so callers can decide how to degrade.
        """
        data = None
        headers = {"Authorization": self._auth_header}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(
            self._url(path), data=data, headers=headers,
            method="POST" if data is not None else "GET",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
        if not body:
            return None
        return json.loads(body.decode("utf-8"))

    def start(self):
        if self.mode != "live":
            return
        user = str(getattr(self.cfg, "bettercap_user", "user"))
        password = str(getattr(self.cfg, "bettercap_pass", "pass"))
        token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
        self._auth_header = "Basic " + token
        iface = str(getattr(self.cfg, "interface", "mon0"))
        # bettercap's /api/session accepts a single command line; chain the
        # recon setup with ';'. This sets the monitor interface, enables the
        # AP/client recon module, and turns on channel hopping.
        cmd = (
            f"set wifi.interface {iface}; "
            "set wifi.recon.channel ''; "  # empty -> hop across all channels
            "wifi.recon on"
        )
        try:
            self._request("/api/session", payload={"cmd": cmd})
            log.info("bettercap live recon started on %s via %s",
                     iface, self._url("/api/session"))
        except Exception as exc:  # noqa: BLE001 - degrade, never crash
            self._degraded = True
            log.error(
                "bettercap live backend unavailable (%s); poll() will return "
                "[] until restart. Ensure bettercap is running with the REST "
                "API enabled at %s.", exc, self._url("/api/session"),
            )

    def poll(self) -> list:
        if self.mode == "sim":
            return self._sim_poll()
        if self._degraded:
            return []
        return self._live_poll()

    def _live_poll(self) -> list:
        """Translate recent bettercap wifi.ap.* events into project dicts.

        Catches *everything* and returns [] on any error so a transient
        bettercap hiccup never propagates out of poll(). Needs validation
        against a live bettercap instance.
        """
        try:
            events = self._request("/api/events")
        except Exception as exc:  # noqa: BLE001
            log.warning("bettercap poll failed (%s); returning no detections", exc)
            return []
        if not events:
            return []

        out: list = []
        seen: set = set()
        max_ts = self._last_ts
        for ev in events:
            if not isinstance(ev, dict):
                continue
            tag = str(ev.get("tag", ""))
            if not tag.startswith("wifi.ap"):
                continue
            ts = str(ev.get("time", ""))
            # Skip events we've already emitted in a prior poll.
            if self._last_ts and ts and ts <= self._last_ts:
                continue
            if ts > max_ts:
                max_ts = ts
            ap = _translate_ap(ev.get("data"))
            if ap is None:
                continue
            bssid = ap["bssid"]
            if bssid in seen:
                continue
            seen.add(bssid)
            out.append({"type": "ap", **ap})

        self._last_ts = max_ts
        return out

    def _sim_poll(self) -> list:
        # Emit AP *detections*; the agent turns each into an encounter and the
        # capture attempt is what produces a handshake (see game/encounter.py).
        if random.random() < 0.35:
            return [{"type": "ap", **_rand_ap()}]
        return []


# -- live event translation -------------------------------------------------
#
# bettercap's wifi AP payload (the "data" of a wifi.ap.new/wifi.ap.* event)
# looks roughly like:
#   {"mac": "aa:bb:..", "hostname": "MyWifi", "encryption": "WPA2",
#    "cipher": "..", "authentication": "..", "wps": {...},
#    "channel": 36, "rssi": -57, "clients": [ {...}, ... ]}
# Field availability varies by bettercap version, so every access is defensive.
# This mapping needs validation on real hardware.

def _translate_ap(data) -> dict | None:
    if not isinstance(data, dict):
        return None
    bssid = data.get("mac") or data.get("bssid")
    if not bssid:
        return None

    ssid = data.get("hostname") or data.get("ssid") or ""

    encryption = _norm_encryption(
        data.get("encryption"),
        data.get("authentication"),
    )

    channel = data.get("channel")
    band = _band_from_channel(channel)

    wps = data.get("wps")
    # bettercap reports wps as a (possibly empty) dict/object when present.
    if isinstance(wps, dict):
        wps_flag = len(wps) > 0
    else:
        wps_flag = bool(wps)

    clients = data.get("clients")
    client_count = len(clients) if isinstance(clients, list) else 0

    rssi = data.get("rssi")
    signal = int(rssi) if isinstance(rssi, (int, float)) else -60

    return {
        "bssid": str(bssid).upper(),
        "ssid": str(ssid),
        "encryption": encryption,
        "band": band,
        "wps": wps_flag,
        "clients": client_count,
        "signal": signal,
    }


def _norm_encryption(encryption, authentication) -> str:
    """Map bettercap's encryption/auth strings to the project's lowercase set
    (open/wep/wpa/wpa2/wpa3/wpa2-eap)."""
    enc = (str(encryption) if encryption else "").strip().lower()
    auth = (str(authentication) if authentication else "").strip().lower()

    if not enc or enc in ("none", "open", ""):
        return "open"
    if "wep" in enc:
        return "wep"
    # EAP / enterprise auth maps to a -eap suffix on the base scheme.
    is_eap = "eap" in auth or "mgt" in auth or "enterprise" in auth
    if "wpa3" in enc:
        return "wpa3-eap" if is_eap else "wpa3"
    if "wpa2" in enc:
        return "wpa2-eap" if is_eap else "wpa2"
    if "wpa" in enc:
        return "wpa2-eap" if is_eap else "wpa"
    return enc


def _band_from_channel(channel) -> str:
    """Derive the band from a WiFi channel number; default to 2.4GHz."""
    try:
        ch = int(channel)
    except (TypeError, ValueError):
        return "2.4GHz"
    if 1 <= ch <= 14:
        return "2.4GHz"
    # 6GHz (Wi-Fi 6E) channels run 1..233 but bettercap reports frequency-
    # derived high channel numbers; treat the typical 5GHz block as 5GHz and
    # the 6E range above it as 6GHz.
    if 32 <= ch <= 177:
        return "5GHz"
    if ch >= 178:
        return "6GHz"
    return "2.4GHz"


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
