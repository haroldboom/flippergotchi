from __future__ import annotations

import math
import random


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
        # TODO: connect to gpsd (JSON protocol, tcp 2947), read TPV lat/lon,
        # and diff against the previous fix with haversine_m().
        return 0.0
