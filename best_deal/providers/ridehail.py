"""Shared implementation for app-based ride-hailing (upfront, surge-priced fares)."""

from __future__ import annotations

from .base import Product, Provider, Quote, Trip, demand_level, jitter, metered, round_fare, time_bucket


class RideHailProvider(Provider):
    products: tuple[Product, ...]
    platform_fee: float
    surge_sensitivity: float  # how strongly demand pushes the multiplier
    surge_cap: float
    base_eta: float  # pickup wait at low demand, minutes
    promo_chance: float = 0.0  # share of time windows with a promo discount
    promo_discount: float = 0.0

    def deeplink(self, trip: Trip) -> str | None:
        return None

    def surge(self, trip: Trip) -> float:
        demand = demand_level(trip.when)
        noise = jitter(self.key, trip.route_key, time_bucket(trip.when), "surge", spread=0.12)
        return round(min(max(1.0 + demand * self.surge_sensitivity + noise, 1.0), self.surge_cap), 2)

    def quote(self, trip: Trip) -> list[Quote]:
        surge = self.surge(trip)
        demand = demand_level(trip.when)
        bucket = time_bucket(trip.when)
        promo = jitter(self.key, trip.route_key, bucket, "promo") > 1 - 2 * self.promo_chance
        quotes = []
        for p in self.products:
            fare = max(metered(p, trip) * surge, p.minimum) + self.platform_fee
            notes = []
            if promo and self.promo_discount:
                fare *= 1 - self.promo_discount
                notes.append(f"promo -{self.promo_discount:.0%}")
            if surge >= 1.3:
                notes.append("high demand")
            fare = round_fare(fare)
            eta = self.base_eta + p.eta_offset + demand * 5 + jitter(self.key, trip.route_key, bucket, p.name, "eta", spread=1.5)
            quotes.append(
                Quote(
                    provider=self.name,
                    product=p.name,
                    seats=p.seats,
                    price=fare,
                    price_low=fare,
                    price_high=fare,
                    pickup_eta_min=round(max(eta, 1.0), 1),
                    trip_min=trip.duration_min,
                    surge=surge,
                    model_price=fare,
                    deeplink=self.deeplink(trip),
                    notes=notes,
                )
            )
        return quotes
