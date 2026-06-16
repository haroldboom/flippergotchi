"""Are we 'home'? Battles (cracking) are only offered at home.

Home = within the configured geofence OR a home network is currently in range.
"""
from __future__ import annotations

from ..pet.gps import haversine_m

WARNING = (
    "WARNING: only BATTLE (crack) networks you OWN or are explicitly authorized "
    "to test. Capturing/collecting is passive; cracking someone else's handshake "
    "without permission is illegal in most places."
)


def at_home(cfg, lat: float | None = None, lon: float | None = None,
            visible_ssids=None) -> bool:
    for s in (visible_ssids or []):
        if any(h and h.lower() in s.lower() for h in cfg.home_networks):
            return True
    loc = getattr(cfg, "home_location", None)
    if loc and len(loc) == 2 and lat is not None and lon is not None:
        return haversine_m(lat, lon, loc[0], loc[1]) <= cfg.home_radius_m
    return False
