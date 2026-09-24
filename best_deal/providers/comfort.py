"""ComfortDelGro via the Zig app: metered taxis (fixed surcharges) plus a flat-fare option."""

from __future__ import annotations

from ..geo import Location, is_near
from .base import Product, Provider, Quote, Trip, demand_level, jitter, round_fare, time_bucket
from .ridehail import RideHailProvider

CHANGI = Location("Changi Airport", 1.3572, 103.9880)


class _ComfortFlatFare(RideHailProvider):
    key = "comfort"
    name = "ComfortDelGro"
    products = (
        Product("Flat Fare Taxi", 4, base=3.90, per_km=0.62, per_min=0.15, minimum=8.0, eta_offset=1.0),
        Product("ComfortRIDE", 4, base=2.80, per_km=0.64, per_min=0.15, minimum=6.5, eta_offset=2.0),
        Product("MaxiCab (Flat)", 6, base=4.50, per_km=0.66, per_min=0.16, minimum=12.0, multiplier=1.4, eta_offset=6.0),
    )
    platform_fee = 0.0
    surge_sensitivity = 0.35
    surge_cap = 1.6
    base_eta = 4.5


class ComfortDelGro(Provider):
    key = "comfort"
    name = "ComfortDelGro"

    FLAG_DOWN = 4.40  # first 1 km
    STEP = 0.26
    BOOKING_FEE_PEAK = 3.30
    BOOKING_FEE_OFFPEAK = 2.30

    def __init__(self) -> None:
        self._flat = _ComfortFlatFare()

    @staticmethod
    def surcharge_rate(trip: Trip) -> tuple[float, str | None]:
        h = trip.when.hour + trip.when.minute / 60
        if h < 6:
            return 0.5, "midnight surcharge +50%"
        if trip.when.weekday() < 5 and 6 <= h < 9.5:
            return 0.25, "peak surcharge +25%"
        if h >= 18:
            return 0.25, "peak surcharge +25%"
        return 0.0, None

    def meter(self, trip: Trip) -> float:
        km = trip.distance_km
        fare = self.FLAG_DOWN
        if km > 1:
            first = min(km, 10) - 1
            fare += self.STEP * -(-first * 1000 // 400)  # per 400m up to 10km
        if km > 10:
            fare += self.STEP * -(-(km - 10) * 1000 // 350)  # per 350m thereafter
        # Waiting time: assume ~20% of the trip is spent below the speed threshold.
        fare += self.STEP * (trip.duration_min * 0.2 * 60 // 45)
        return fare

    def metered_quote(self, trip: Trip) -> Quote:
        rate, surcharge_note = self.surcharge_rate(trip)
        fare = self.meter(trip) * (1 + rate)
        notes = ["metered: final fare varies with traffic"]
        if surcharge_note:
            notes.append(surcharge_note)
        peak = rate > 0 or demand_level(trip.when) >= 0.75
        fare += self.BOOKING_FEE_PEAK if peak else self.BOOKING_FEE_OFFPEAK
        if is_near(trip.origin, CHANGI, 2.5):
            airport = 8.0 if 17 <= trip.when.hour < 24 else 6.0
            fare += airport
            notes.append(f"airport surcharge ${airport:.0f}")
        mid = round_fare(fare)
        eta = 5.0 + demand_level(trip.when) * 6 + jitter(self.key, trip.route_key, time_bucket(trip.when), "meter-eta", spread=1.5)
        return Quote(
            provider=self.name,
            product="Metered Taxi",
            seats=4,
            price=mid,
            price_low=round_fare(mid * 0.92),
            price_high=round_fare(mid * 1.12),
            pickup_eta_min=round(max(eta, 1.0), 1),
            trip_min=trip.duration_min,
            surge=round(1 + rate, 2),
            model_price=mid,
            notes=notes,
        )

    def quote(self, trip: Trip) -> list[Quote]:
        return [self.metered_quote(trip), *self._flat.quote(trip)]

