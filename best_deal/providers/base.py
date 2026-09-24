"""Provider interface and the shared demand model used by the fare estimators.

None of Grab, Gojek or ComfortDelGro publish a public fare API, so the built-in
providers are *estimators*: published/observed fare structures plus a demand
(surge) model. Real prices you see in the apps can be recorded as observations;
those calibrate the estimators and feed the insights. A provider that can fetch
live quotes (e.g. a partner API) just implements `Provider.quote` and returns
quotes with source="live".
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime

from ..geo import Location


@dataclass
class Trip:
    origin: Location
    destination: Location
    distance_km: float
    duration_min: float
    when: datetime  # timezone-aware local time
    route_key: str


@dataclass
class Quote:
    provider: str
    product: str
    seats: int
    price: float
    price_low: float
    price_high: float
    pickup_eta_min: float
    trip_min: float
    surge: float = 1.0
    source: str = "estimate"  # estimate | observed | live
    model_price: float | None = None  # uncalibrated estimate, used for calibration
    currency: str = "SGD"
    deeplink: str | None = None
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Product:
    name: str
    seats: int
    base: float
    per_km: float
    per_min: float
    minimum: float
    multiplier: float = 1.0  # vehicle-class premium applied to the metered part
    eta_offset: float = 0.0  # extra pickup wait (e.g. fewer XL cars)


class Provider(ABC):
    key: str
    name: str

    @abstractmethod
    def quote(self, trip: Trip) -> list[Quote]:
        """Return one quote per product available for this trip."""


def demand_level(when: datetime) -> float:
    """Expected demand in [0, 1] for a local time: peaks, late nights, weekends."""
    h = when.hour + when.minute / 60
    wd = when.weekday()
    weekday = wd < 5
    if weekday and 7 <= h < 9.5:
        level = 0.8
    elif weekday and 17.5 <= h < 20:
        level = 0.9
    elif wd in (4, 5) and (h >= 22 or h < 2):  # Fri/Sat nights
        level = 0.75
    elif 0 <= h < 6:
        level = 0.45 if h < 2 else 0.2
    elif 11.5 <= h < 14:
        level = 0.4
    elif not weekday and 10 <= h < 22:
        level = 0.5
    else:
        level = 0.25
    return level


def jitter(*parts: object, spread: float = 1.0) -> float:
    """Deterministic pseudo-random value in [-spread, spread] for the given key.

    Keyed on provider, route and a 15-minute time bucket so repeated searches in
    the same window return consistent prices, like the real apps do.
    """
    digest = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return (int.from_bytes(digest[:8], "big") / 2**64 * 2 - 1) * spread


def time_bucket(when: datetime) -> str:
    return when.strftime("%Y-%m-%d %H:") + f"{when.minute // 15:02d}"


def metered(product: Product, trip: Trip) -> float:
    variable = trip.distance_km * product.per_km + trip.duration_min * product.per_min
    return product.base + variable * product.multiplier


def round_fare(value: float) -> float:
    return round(value * 10) / 10
