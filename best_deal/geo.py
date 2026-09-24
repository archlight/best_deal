"""Geometry helpers: distances, route keys and travel-time estimates."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

EARTH_RADIUS_KM = 6371.0088
# Straight-line distance understates road distance; Singapore's grid averages ~1.3x.
ROAD_DETOUR_FACTOR = 1.3


@dataclass(frozen=True)
class Location:
    name: str
    lat: float
    lng: float

    def as_dict(self) -> dict:
        return {"name": self.name, "lat": self.lat, "lng": self.lng}


def haversine_km(a: Location, b: Location) -> float:
    lat1, lng1, lat2, lng2 = map(math.radians, (a.lat, a.lng, b.lat, b.lng))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def road_distance_km(a: Location, b: Location) -> float:
    return round(max(haversine_km(a, b) * ROAD_DETOUR_FACTOR, 0.5), 2)


def average_speed_kmh(when: datetime) -> float:
    """Rough city driving speed by time of day (peak traffic is slower)."""
    hour = when.hour + when.minute / 60
    weekday = when.weekday() < 5
    if weekday and (7 <= hour < 9.5 or 17.5 <= hour < 20):
        return 24.0
    if 0 <= hour < 6:
        return 45.0
    return 33.0


def trip_duration_min(distance_km: float, when: datetime) -> float:
    # Fixed overhead for pickup manoeuvres, lights and drop-off.
    return round(distance_km / average_speed_kmh(when) * 60 + 3, 1)


def route_key(a: Location, b: Location) -> str:
    """Stable key grouping trips between the same ~100m cells."""
    return f"{a.lat:.3f},{a.lng:.3f}>{b.lat:.3f},{b.lng:.3f}"


def is_near(a: Location, b: Location, radius_km: float) -> bool:
    return haversine_km(a, b) <= radius_km
