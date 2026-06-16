from __future__ import annotations

import json
import math
import random
import socket


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


class GpsReader:
    """Reports metres travelled since the previous poll.

    mode="sim"  -> random wander, for dev on a box with no GPS
    mode="gpsd" -> TODO: read TPV fixes from gpsd on the Flipper One
    mode="off"  -> always 0 (pet never "walks")
    """

    def __init__(self, cfg):
        self.cfg = cfg
        self.mode = cfg.gps_mode
        self._lat = -31.95   # arbitrary start; only the simulator uses it
        self._lon = 115.86
        # gpsd state (lazy): connection is opened on first _gpsd_step() call,
        # never at import/construction time, so the module imports cleanly with
        # no GPS hardware or daemon present.
        self._sock = None          # type: socket.socket | None
        self._buf = b""            # partial-line read buffer
        self._gps_prev = None      # last (lat, lon) fix seen, or None

    def distance(self) -> float:
        if self.mode == "sim":
            return self._sim_step()
        if self.mode == "gpsd":
            return self._gpsd_step()
        return 0.0

    def _sim_step(self) -> float:
        if random.random() < 0.3:
            return 0.0  # standing still
        dlat = random.uniform(-1, 1) * 5e-5
        dlon = random.uniform(-1, 1) * 5e-5
        nlat, nlon = self._lat + dlat, self._lon + dlon
        d = haversine_m(self._lat, self._lon, nlat, nlon)
        self._lat, self._lon = nlat, nlon
        return d

    def _gpsd_step(self) -> float:
        # Read the latest TPV fix from gpsd (JSON protocol over TCP, default
        # 127.0.0.1:2947) and return metres travelled since the previous fix.
        #
        # NB: this path has only been exercised against the gpsd JSON shape from
        # docs/sim; it still needs validation against a real gpsd running on the
        # Flipper One (verify TPV mode>=2 fixes, lat/lon keys, and that a short
        # socket timeout doesn't starve the reader on the device's CPU).
        #
        # Any failure (no daemon, bad data, dropped connection, ...) is caught
        # below and turns into a harmless 0.0 so distance() never raises.
        try:
            if self._sock is None:
                self._connect_gpsd()

            latest = None  # latest (lat, lon) parsed from this poll's TPVs
            for line in self._read_lines():
                try:
                    report = json.loads(line)
                except (ValueError, TypeError):
                    continue  # non-JSON / partial junk line, skip it
                if not isinstance(report, dict):
                    continue
                if report.get("class") != "TPV":
                    continue
                lat = report.get("lat")
                lon = report.get("lon")
                if lat is None or lon is None:
                    continue  # no-fix TPV (mode 0/1) carries no lat/lon
                latest = (float(lat), float(lon))

            if latest is None:
                return 0.0  # no new fix this poll; nothing travelled to report

            prev = self._gps_prev
            self._gps_prev = latest
            if prev is None:
                return 0.0  # first fix: establish a baseline, no distance yet
            return haversine_m(prev[0], prev[1], latest[0], latest[1])
        except Exception:
            # Reset the connection on any error; the next poll reconnects.
            self._reset_gpsd()
            return 0.0

    def _connect_gpsd(self) -> None:
        host = getattr(self.cfg, "gpsd_host", "127.0.0.1")
        port = getattr(self.cfg, "gpsd_port", 2947)
        sock = socket.create_connection((host, port), timeout=2.0)
        # Short timeout makes subsequent reads non-blocking-ish: we drain
        # whatever lines are already buffered, then bail on the next recv.
        sock.settimeout(0.2)
        # Ask gpsd to stream JSON TPV reports.
        sock.sendall(b'?WATCH={"enable":true,"json":true}\n')
        self._sock = sock
        self._buf = b""

    def _read_lines(self):
        # Yield complete newline-terminated lines currently available on the
        # socket. Stops once recv times out (no more data ready) or the peer
        # closes. Leftover partial data is kept in self._buf for next time.
        while True:
            try:
                chunk = self._sock.recv(4096)
            except socket.timeout:
                break  # nothing more ready right now
            if not chunk:
                # Peer closed; force a reconnect on the next poll.
                self._reset_gpsd()
                break
            self._buf += chunk
            while b"\n" in self._buf:
                line, self._buf = self._buf.split(b"\n", 1)
                yield line.decode("utf-8", "replace").strip()

    def _reset_gpsd(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
        self._sock = None
        self._buf = b""
