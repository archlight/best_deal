from __future__ import annotations

import urllib.parse

from .base import Product, Trip
from .ridehail import RideHailProvider


class Grab(RideHailProvider):
    key = "grab"
    name = "Grab"
    products = (
        Product("GrabCar Saver", 4, base=2.50, per_km=0.62, per_min=0.14, minimum=6.0, eta_offset=3.0),
        Product("JustGrab", 4, base=3.00, per_km=0.70, per_min=0.18, minimum=7.0),
        Product("GrabCar 6", 6, base=3.50, per_km=0.70, per_min=0.18, minimum=10.0, multiplier=1.35, eta_offset=2.0),
        Product("GrabCar Premium", 4, base=4.50, per_km=0.70, per_min=0.18, minimum=14.0, multiplier=1.6, eta_offset=2.5),
    )
    platform_fee = 0.90
    surge_sensitivity = 0.55
    surge_cap = 2.0
    base_eta = 3.0
    promo_chance = 0.08
    promo_discount = 0.10

    def deeplink(self, trip: Trip) -> str:
        params = urllib.parse.urlencode({
            "screenType": "BOOKING",
            "pickUpLatitude": trip.origin.lat,
            "pickUpLongitude": trip.origin.lng,
            "dropOffLatitude": trip.destination.lat,
            "dropOffLongitude": trip.destination.lng,
        })
        return f"grab://open?{params}"
