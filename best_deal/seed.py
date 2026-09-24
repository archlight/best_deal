"""Generate a synthetic search history so the insights views have something to show."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from . import config, service
from .places import PLACES
from .storage import Store

DEFAULT_ROUTES = [
    ("Changi Airport T3", "Marina Bay Sands"),
    ("Tampines", "Raffles Place"),
    ("Jurong East", "one-north"),
    ("Orchard Road (ION)", "Sentosa"),
    ("Punggol", "Novena"),
]


def seed(store: Store, days: int = 28, per_day: int = 12, observed_share: float = 0.15, rng_seed: int = 7) -> int:
    """Record `days * per_day` searches spread over past days and hours.

    A share of searches also get an "observed" price (estimate +/- noise with a small
    provider bias) so calibration and observed-only insights can be exercised.
    """
    rng = random.Random(rng_seed)
    names = {p.name for p in PLACES}
    routes = [r for r in DEFAULT_ROUTES if r[0] in names and r[1] in names]
    bias = {"Grab": 1.06, "Gojek": 0.97, "ComfortDelGro": 1.02}
    start = datetime.now(config.TIMEZONE).replace(minute=0, second=0, microsecond=0) - timedelta(days=days)
    count = 0
    for day in range(days):
        for _ in range(per_day):
            origin, dest = rng.choice(routes)
            if rng.random() < 0.5:
                origin, dest = dest, origin
            when = start + timedelta(days=day, hours=rng.choice(range(24)), minutes=rng.choice((0, 15, 30, 45)))
            result = service.search(store, origin, dest, when)
            count += 1
            if rng.random() < observed_share:
                q = rng.choice([q for q in result["quotes"] if q["source"] == "estimate"])
                price = q["model_price"] * bias.get(q["provider"], 1) * rng.uniform(0.93, 1.07)
                service.record_observation(store, result["search_id"], q["provider"], q["product"], round(price, 1))
    return count
