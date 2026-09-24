from __future__ import annotations

from .base import Product
from .ridehail import RideHailProvider


class Gojek(RideHailProvider):
    key = "gojek"
    name = "Gojek"
    products = (
        Product("GoCar Economy", 4, base=2.40, per_km=0.60, per_min=0.13, minimum=6.0, eta_offset=2.5),
        Product("GoCar", 4, base=2.80, per_km=0.66, per_min=0.16, minimum=6.5),
        Product("GoCar XL", 6, base=3.50, per_km=0.66, per_min=0.16, minimum=10.0, multiplier=1.4, eta_offset=3.0),
    )
    platform_fee = 0.60
    surge_sensitivity = 0.45
    surge_cap = 1.8
    base_eta = 4.0
    promo_chance = 0.15
    promo_discount = 0.12
