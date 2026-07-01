from __future__ import annotations

import base64
import json
import logging
import random
import time
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

    def __init__(self, cfg, is_authorized=None):
        self.cfg = cfg
        self.mode = "sim" if cfg.simulate else "live"
        # Per-target gate for the ONLY active/transmitting action this client
        # performs (deauth). Without it the live path would deauth on every
        # capture regardless of consent/scope; mirrors the native backend.
        self._is_authorized = is_authorized
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
        user = str(getattr(self.cfg, "bettercap_user", ""))
        password = str(getattr(self.cfg, "bettercap_pass", ""))
        if not user and not password:
            log.warning(
                "bettercap REST credentials are unset (cfg.bettercap_user / "
                "cfg.bettercap_pass); set them to match your bettercap "
                "`api.rest` config or live capture will 401.")
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

    def capture_handshake(self, bssid, ssid="", timeout=25):
        """Actively capture a WPA handshake for ``bssid`` and return its .pcap.

        This is what an on-device "capture" action calls: in live mode it
        focuses recon on the AP's channel, fires a deauth to nudge a client
        into re-associating, then polls /api/events for a
        ``wifi.client.handshake`` event whose AP mac matches ``bssid``. On
        success it returns a best-effort path to the .pcap bettercap wrote
        (the event's ``file`` field if present, otherwise a path derived from
        wifi.handshakes.file). Returns None in sim mode or on ANY error.

        NEEDS ON-HARDWARE VALIDATION: bettercap event tags/payload shapes and
        the handshakes-file layout vary by version, so every access is guarded
        and the method degrades to None rather than raising.
        """
        if self.mode != "live" or self._degraded:
            return None
        try:
            return self._capture_handshake_live(bssid, ssid, timeout)
        except Exception as exc:  # noqa: BLE001 - never raise out of capture
            log.warning("bettercap capture_handshake failed (%s); no capture", exc)
            return None

    def _capture_handshake_live(self, bssid, ssid, timeout):
        if not bssid:
            return None
        target = str(bssid).lower()
        try:
            deadline = float(timeout)
        except (TypeError, ValueError):
            deadline = 25.0

        # Best-effort: lock recon onto the AP's channel (if we know it from a
        # prior detection) and deauth the AP to force handshakes. The channel
        # may be unknown; bettercap tolerates targeting by bssid regardless.
        channel = self._known_channel(target)
        cmds = []
        if channel:
            cmds.append(f"wifi.recon.channel {channel}")
        # Deauth is the only transmitting action here. Gate it PER TARGET and
        # suppress it entirely under --dry-run, exactly like the native backend
        # -- when it's not allowed we still listen passively for a handshake.
        active = self._authorized(target, ssid)
        if bool(getattr(self.cfg, "dry_run", False)):
            if active:
                log.info("DRY-RUN: would deauth authorized target %s -- "
                         "SUPPRESSED (passive listen only)", target)
            active = False
        elif not active:
            log.info("bettercap capture for %s is PASSIVE-only (not an "
                     "authorized/in-scope target): no deauth sent", target)
        if active:
            cmds.append(f"wifi.deauth {target}")
        for cmd in cmds:
            try:
                self._request("/api/session", payload={"cmd": cmd})
            except Exception as exc:  # noqa: BLE001 - keep polling regardless
                log.debug("bettercap capture cmd %r failed (%s)", cmd, exc)

        end = time.monotonic() + deadline
        while time.monotonic() < end:
            try:
                events = self._request("/api/events") or []
            except Exception as exc:  # noqa: BLE001
                log.debug("bettercap capture poll failed (%s)", exc)
                events = []
            for ev in events:
                if not isinstance(ev, dict):
                    continue
                tag = str(ev.get("tag", ""))
                if "handshake" not in tag:
                    continue
                data = ev.get("data")
                if not isinstance(data, dict):
                    continue
                ap = data.get("ap") or data.get("bssid") or data.get("mac") or ""
                if str(ap).lower() != target:
                    continue
                path = self._handshake_path(data, target)
                if path:
                    return path
                # handshake seen but no resolvable path -> still a best-effort
                # signal; return the configured handshakes file if any.
                return self._handshakes_file() or None
            time.sleep(0.5)
        return None

    def _authorized(self, bssid, ssid) -> bool:
        """Consult the per-target gate; a missing or broken gate fails CLOSED
        (passive), so we never transmit without an explicit yes."""
        if self._is_authorized is None:
            return False
        try:
            return bool(self._is_authorized(bssid, ssid))
        except Exception as exc:  # noqa: BLE001 - a broken gate must fail CLOSED
            log.warning("bettercap authorization callback raised (%s); "
                        "treating as DENIED", exc)
            return False

    def _known_channel(self, bssid_lower):
        """Channel cached from a prior detection, if the agent recorded one."""
        cache = getattr(self, "_channels", None)
        if isinstance(cache, dict):
            return cache.get(bssid_lower)
        return None

    def _handshake_path(self, data, target):
        """Resolve a .pcap path from a handshake event payload."""
        for key in ("file", "path", "pcap", "filename"):
            val = data.get(key)
            if val and isinstance(val, str):
                return val
        return None

    def _handshakes_file(self):
        """bettercap's configured wifi.handshakes.file, best-effort."""
        val = getattr(self.cfg, "handshakes_file", "")
        return str(val) if val else ""

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

# encryptions that are potentially crackable with a wordlist (everything else,
# e.g. WPA3/SAE, WPA2-Enterprise, OWE, is not surfaced as a monster)
CRACKABLE = ("open", "wep", "wpa", "wpa2")


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
    if encryption not in CRACKABLE:    # skip WPA3/Enterprise/OWE -- not crackable
        return None

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
        # only crackable encryptions -- WPA3/Enterprise aren't wordlist-crackable,
        # so they're not surfaced as monsters at all
        "encryption": random.choice(
            ["wpa2", "wpa2", "wpa2", "wpa2", "wpa", "open", "wep"]),
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
