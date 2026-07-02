from __future__ import annotations

import json
import math
import random
import socket
from datetime import datetime

# --- Real-fix sanity clamps ---------------------------------------------------
# The Flipper One has NO onboard GPS/GNSS and NO IMU/accelerometer (see the
# official tech specs: https://docs.flipper.net/one/general/tech-specs), so the
# "gpsd" path can only ever consume fixes from an *externally* attached USB/UART
# GPS. External consumer GPS is noisy: a single glitched TPV can otherwise inject
# unbounded metres straight into the walk->XP/scrap/forage economy. These
# module-level constants bound what one poll is allowed to contribute.
MIN_TPV_MODE = 2          # accept only 2D (>=2) or 3D (3) fixes; drop mode 0/1
MAX_WALK_SPEED_MPS = 3.0  # ~10.8 km/h: brisk jog; nobody *walks* the shark faster
MAX_TELEPORT_M = 300.0    # a >300 m single-step jump is a GPS glitch, not a walk
MAX_ACCURACY_M = 50.0     # if epx/epy reported and worse than this, distrust the fix
DEFAULT_POLL_INTERVAL_S = 5.0  # speed-cap fallback when TPVs carry no usable time


def _tpv_epoch(report):
    """Parse a TPV 'time' (ISO-8601, e.g. '2026-07-02T12:00:00.000Z') to epoch
    seconds, or return None if it is missing/unparseable."""
    t = report.get("time")
    if not isinstance(t, str):
        return None
    try:
        # gpsd emits a trailing 'Z'; fromisoformat wants an explicit offset.
        return datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None


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
    mode="gpsd" -> read TPV fixes from gpsd (implemented; needs on-device
                   validation with an *external* GPS -- the Flipper One has no
                   onboard GNSS or IMU). Fixes are sanity-clamped before they
                   feed the walk economy; see _gpsd_step and the MAX_* constants.
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
        self._gps_prev = None      # last accepted (lat, lon) fix, or None
        self._gps_prev_t = None    # epoch secs of last accepted fix, or None

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
        # Implemented; still needs validation against a real gpsd running on the
        # Flipper One with an EXTERNAL GPS (the device has no onboard GNSS/IMU --
        # docs.flipper.net/one/general/tech-specs). Because consumer GPS is noisy
        # and this number feeds the walk->XP/scrap/forage economy directly, every
        # candidate fix is sanity-clamped before it counts:
        #   * only mode>=2 (2D/3D) TPVs are trusted; mode 0/1 no-fix reports drop;
        #   * fixes with reported epx/epy worse than MAX_ACCURACY_M are distrusted;
        #   * a single-step jump over MAX_TELEPORT_M is treated as a glitch and
        #     re-baselines (0 m) instead of dumping hundreds of metres into XP;
        #   * the remaining distance is capped at MAX_WALK_SPEED_MPS * elapsed so
        #     no poll can credit more walking than a human could plausibly do.
        #
        # Any failure (no daemon, bad data, dropped connection, ...) is caught
        # below and turns into a harmless 0.0 so distance() never raises.
        try:
            if self._sock is None:
                self._connect_gpsd()

            latest = None  # latest accepted (lat, lon) parsed this poll
            latest_t = None  # its epoch time, if the TPV carried one
            for line in self._read_lines():
                try:
                    report = json.loads(line)
                except (ValueError, TypeError):
                    continue  # non-JSON / partial junk line, skip it
                if not isinstance(report, dict):
                    continue
                if report.get("class") != "TPV":
                    continue
                # Reject no-fix / dead-reckoning-only fixes: only 2D/3D counts.
                try:
                    mode = int(report.get("mode", 0))
                except (TypeError, ValueError):
                    mode = 0
                if mode < MIN_TPV_MODE:
                    continue
                lat = report.get("lat")
                lon = report.get("lon")
                if lat is None or lon is None:
                    continue  # a mode>=2 TPV should carry lat/lon; be defensive
                # Distrust fixes whose reported horizontal error is too large.
                if not self._accuracy_ok(report):
                    continue
                latest = (float(lat), float(lon))
                latest_t = _tpv_epoch(report)

            if latest is None:
                return 0.0  # no trustworthy fix this poll; nothing to report

            prev = self._gps_prev
            prev_t = self._gps_prev_t
            self._gps_prev = latest
            self._gps_prev_t = latest_t
            if prev is None:
                return 0.0  # first fix: establish a baseline, no distance yet

            dist = haversine_m(prev[0], prev[1], latest[0], latest[1])
            # Teleport: a jump this big is a GPS glitch or a post-gap reacquire.
            # Drop the distance and let the new position be the fresh baseline.
            if dist > MAX_TELEPORT_M:
                return 0.0
            # Speed cap: never credit more than a human could walk/jog in the
            # elapsed time (falling back to a fixed per-poll cap when we have no
            # usable timestamps on either fix).
            if latest_t is not None and prev_t is not None and latest_t > prev_t:
                elapsed = latest_t - prev_t
            else:
                elapsed = DEFAULT_POLL_INTERVAL_S
            cap = MAX_WALK_SPEED_MPS * elapsed
            return min(dist, cap)
        except Exception:
            # Reset the connection on any error; the next poll reconnects.
            self._reset_gpsd()
            return 0.0

    @staticmethod
    def _accuracy_ok(report) -> bool:
        # If gpsd reports estimated horizontal error (epx/epy, metres), require
        # both to be within MAX_ACCURACY_M. Absent fields => accept (many GPS
        # units don't emit them); non-numeric => reject as untrustworthy.
        for key in ("epx", "epy"):
            val = report.get(key)
            if val is None:
                continue
            try:
                if float(val) > MAX_ACCURACY_M:
                    return False
            except (TypeError, ValueError):
                return False
        return True

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
        # A dropped/reconnected link is a gap: forget the old position so the
        # next fix re-baselines instead of reporting a teleport across the gap.
        self._gps_prev = None
        self._gps_prev_t = None
