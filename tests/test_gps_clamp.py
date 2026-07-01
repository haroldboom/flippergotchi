"""GPS real-fix sanity-clamp checks for the gpsd path.

The Flipper One has no onboard GPS/GNSS or IMU, so gpsd can only ever consume
fixes from an externally attached GPS. Consumer GPS is noisy, and gps.distance()
feeds the walk->XP/scrap/forage economy directly, so `_gpsd_step` sanity-clamps
every candidate fix. These tests drive that path with synthetic TPV lines, no
real gpsd: we bypass the socket by stubbing `_connect_gpsd` and `_read_lines`.

Run with `python -m pytest` or `python tests/test_gps_clamp.py`.
"""
from __future__ import annotations

import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flippergotchi.pet import gps
from flippergotchi.pet.gps import GpsReader, haversine_m


def _make_reader():
    cfg = SimpleNamespace(gps_mode="gpsd", gpsd_host="127.0.0.1", gpsd_port=2947)
    reader = GpsReader(cfg)
    # Never touch a real socket: pretend we're connected and hand the reader
    # whatever TPV lines the test queued.
    reader._connect_gpsd = lambda: setattr(reader, "_sock", object())
    return reader


def _feed(reader, reports):
    """Queue a batch of dict reports as the lines the next poll will read."""
    lines = [json.dumps(r) for r in reports]
    reader._read_lines = lambda: iter(lines)


def _tpv(lat, lon, mode=3, t=None, **extra):
    r = {"class": "TPV", "mode": mode, "lat": lat, "lon": lon}
    if t is not None:
        r["time"] = t
    r.update(extra)
    return r


# A pair of nearby points ~7 m apart (a normal walking step over a few seconds).
LAT0, LON0 = -31.95000, 115.86000
LAT1, LON1 = -31.95000, 115.86008  # ~7.5 m east at this latitude


def test_first_fix_is_baseline_only():
    reader = _make_reader()
    _feed(reader, [_tpv(LAT0, LON0)])
    assert reader.distance() == 0.0  # first fix establishes baseline, no distance


def test_normal_walking_step_accepted():
    reader = _make_reader()
    _feed(reader, [_tpv(LAT0, LON0, t="2026-07-02T12:00:00Z")])
    reader.distance()  # baseline
    _feed(reader, [_tpv(LAT1, LON1, t="2026-07-02T12:00:05Z")])
    d = reader.distance()
    expected = haversine_m(LAT0, LON0, LAT1, LON1)
    assert d > 0.0
    assert abs(d - expected) < 1e-6  # a plausible step passes through unchanged


def test_mode_below_2_rejected():
    reader = _make_reader()
    _feed(reader, [_tpv(LAT0, LON0)])
    reader.distance()  # baseline
    # A no-fix (mode 1) TPV carries lat/lon garbage but must not count at all,
    # and must not overwrite the trusted baseline.
    _feed(reader, [_tpv(LAT1, LON1, mode=1)])
    assert reader.distance() == 0.0
    assert reader._gps_prev == (LAT0, LON0)


def test_teleport_jump_dropped():
    reader = _make_reader()
    _feed(reader, [_tpv(LAT0, LON0)])
    reader.distance()  # baseline
    # Jump ~1 km away in one poll -> glitch. Distance is dropped (0), and the
    # new position becomes the fresh baseline so we don't teleport back either.
    far_lat, far_lon = LAT0 + 0.01, LON0  # ~1.1 km north
    assert haversine_m(LAT0, LON0, far_lat, far_lon) > gps.MAX_TELEPORT_M
    _feed(reader, [_tpv(far_lat, far_lon)])
    assert reader.distance() == 0.0
    assert reader._gps_prev == (far_lat, far_lon)


def test_per_poll_distance_capped_by_speed():
    reader = _make_reader()
    _feed(reader, [_tpv(LAT0, LON0, t="2026-07-02T12:00:00Z")])
    reader.distance()  # baseline
    # Move ~250 m (< teleport threshold, so not dropped) but in only 2 s: that
    # implies ~125 m/s, far above MAX_WALK_SPEED_MPS. Expect it clamped to
    # MAX_WALK_SPEED_MPS * elapsed.
    fast_lat = LAT0 + 0.00225  # ~250 m north
    raw = haversine_m(LAT0, LON0, fast_lat, LON0)
    assert raw < gps.MAX_TELEPORT_M  # not a teleport; the speed cap must catch it
    assert raw > gps.MAX_WALK_SPEED_MPS * 2.0
    _feed(reader, [_tpv(fast_lat, LON0, t="2026-07-02T12:00:02Z")])
    d = reader.distance()
    assert abs(d - gps.MAX_WALK_SPEED_MPS * 2.0) < 1e-6


def test_speed_cap_fallback_without_timestamps():
    reader = _make_reader()
    _feed(reader, [_tpv(LAT0, LON0)])  # no time field
    reader.distance()  # baseline
    fast_lat = LAT0 + 0.00225  # ~250 m, no timestamps -> fixed-interval fallback
    _feed(reader, [_tpv(fast_lat, LON0)])
    d = reader.distance()
    assert abs(d - gps.MAX_WALK_SPEED_MPS * gps.DEFAULT_POLL_INTERVAL_S) < 1e-6


def test_poor_accuracy_fix_rejected():
    reader = _make_reader()
    _feed(reader, [_tpv(LAT0, LON0)])
    reader.distance()  # baseline
    # epx/epy worse than MAX_ACCURACY_M -> distrust the fix entirely.
    _feed(reader, [_tpv(LAT1, LON1, epx=200.0, epy=5.0)])
    assert reader.distance() == 0.0
    assert reader._gps_prev == (LAT0, LON0)


def test_good_accuracy_fix_accepted():
    reader = _make_reader()
    _feed(reader, [_tpv(LAT0, LON0, t="2026-07-02T12:00:00Z", epx=5.0, epy=5.0)])
    reader.distance()  # baseline
    _feed(reader, [_tpv(LAT1, LON1, t="2026-07-02T12:00:05Z", epx=5.0, epy=5.0)])
    d = reader.distance()
    assert abs(d - haversine_m(LAT0, LON0, LAT1, LON1)) < 1e-6


def test_sim_mode_unchanged():
    # The clamp work must not touch the simulator the rest of the suite relies on.
    cfg = SimpleNamespace(gps_mode="sim", gpsd_host="127.0.0.1", gpsd_port=2947)
    reader = GpsReader(cfg)
    for _ in range(50):
        assert reader.distance() >= 0.0  # sim wander stays finite and non-negative


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
