"""Search orchestration: build the trip, gather quotes, calibrate, rank and record."""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta

from . import config, places
from .geo import Location, road_distance_km, route_key, trip_duration_min
from .providers import REGISTRY, Provider, Quote, Trip
from .storage import Store


def make_trip(origin: Location, destination: Location, when: datetime | None = None) -> Trip:
    if when is None:
        when = datetime.now(config.TIMEZONE)
    elif when.tzinfo is None:
        when = when.replace(tzinfo=config.TIMEZONE)
    else:
        when = when.astimezone(config.TIMEZONE)
    distance = road_distance_km(origin, destination)
    return Trip(origin, destination, distance, trip_duration_min(distance, when), when, route_key(origin, destination))


def calibration_factors(store: Store, min_samples: int | None = None) -> dict[tuple[str, str], dict]:
    """Median observed/estimated ratio per (provider, product), once enough observations exist."""
    min_samples = config.CALIBRATION_MIN_SAMPLES if min_samples is None else min_samples
    ratios: dict[tuple[str, str], list[float]] = {}
    for row in store.calibration_pairs():
        ratios.setdefault((row["provider"], row["product"]), []).append(row["observed"] / row["estimated"])
    return {
        key: {"factor": round(statistics.median(vals), 3), "samples": len(vals)}
        for key, vals in ratios.items()
        if len(vals) >= min_samples
    }


def apply_calibration(quotes: list[Quote], factors: dict[tuple[str, str], dict]) -> None:
    for q in quotes:
        cal = factors.get((q.provider, q.product))
        if not cal or q.source != "estimate":
            continue
        f = cal["factor"]
        q.price = round(q.price * f, 1)
        q.price_low = round(q.price_low * f, 1)
        q.price_high = round(q.price_high * f, 1)
        q.notes.append(f"calibrated x{f:.2f} from {cal['samples']} observed fares")


def rank(quotes: list[Quote]) -> dict[str, dict]:
    """Skyscanner-style labels: cheapest, fastest (pickup + ride) and best value."""
    if not quotes:
        return {}
    total_time = lambda q: q.pickup_eta_min + q.trip_min  # noqa: E731
    cheapest = min(quotes, key=lambda q: q.price)
    fastest = min(quotes, key=total_time)
    lo_p, hi_p = cheapest.price, max(q.price for q in quotes)
    lo_t, hi_t = total_time(fastest), max(total_time(q) for q in quotes)

    def score(q: Quote) -> float:
        # Price weighs more than time; both normalised to [0, 1] across results.
        p = (q.price - lo_p) / (hi_p - lo_p) if hi_p > lo_p else 0
        t = (total_time(q) - lo_t) / (hi_t - lo_t) if hi_t > lo_t else 0
        return 0.7 * p + 0.3 * t

    best = min(quotes, key=score)
    return {
        "cheapest": {"provider": cheapest.provider, "product": cheapest.product, "price": cheapest.price},
        "fastest": {"provider": fastest.provider, "product": fastest.product, "minutes": round(total_time(fastest), 1)},
        "best": {"provider": best.provider, "product": best.product, "price": best.price},
    }


def search(
    store: Store,
    origin: str | dict | Location,
    destination: str | dict | Location,
    when: datetime | None = None,
    providers: list[str] | None = None,
    record: bool = True,
) -> dict:
    o, d = places.resolve(origin), places.resolve(destination)
    trip = make_trip(o, d, when)
    selected: list[Provider] = [REGISTRY[k] for k in (providers or REGISTRY) if k in REGISTRY]
    quotes = [q for p in selected for q in p.quote(trip)]
    apply_calibration(quotes, calibration_factors(store))
    quotes.sort(key=lambda q: (q.price, q.pickup_eta_min))

    search_id = None
    quote_ids: list[int | None] = [None] * len(quotes)
    if record:
        search_id = store.add_search(trip)
        quote_ids = store.add_quotes(search_id, quotes)

    return {
        "search_id": search_id,
        "trip": {
            "origin": o.as_dict(),
            "destination": d.as_dict(),
            "distance_km": trip.distance_km,
            "duration_min": trip.duration_min,
            "when": trip.when.isoformat(timespec="minutes"),
            "route_key": trip.route_key,
        },
        "quotes": [{**q.as_dict(), "id": qid} for q, qid in zip(quotes, quote_ids)],
        "labels": rank(quotes),
    }


def record_observation(
    store: Store,
    search_id: int,
    provider: str,
    product: str,
    price: float,
    pickup_eta_min: float | None = None,
    seats: int | None = None,
) -> dict:
    """Record a price actually seen in a provider's app for an earlier search."""
    found = store.get_search(search_id)
    if not found:
        raise LookupError(f"search {search_id} not found")
    if price <= 0:
        raise ValueError("price must be positive")
    estimate = next(
        (q for q in found["quotes"] if q["provider"] == provider and q["product"] == product and q["source"] == "estimate"),
        None,
    )
    quote = Quote(
        provider=provider,
        product=product,
        seats=seats or (estimate["seats"] if estimate else 4),
        price=round(price, 2),
        price_low=round(price, 2),
        price_high=round(price, 2),
        pickup_eta_min=pickup_eta_min if pickup_eta_min is not None else (estimate["pickup_eta_min"] if estimate else 0),
        trip_min=found["duration_min"],
        surge=estimate["surge"] if estimate else 1.0,
        source="observed",
        currency=config.CURRENCY,
    )
    [qid] = store.add_quotes(search_id, [quote])
    result = {**quote.as_dict(), "id": qid, "search_id": search_id}
    if estimate and estimate["model_price"]:
        result["estimate_error_pct"] = round((price / estimate["model_price"] - 1) * 100, 1)
    return result


def timeline(
    store: Store,
    origin: str | dict | Location,
    destination: str | dict | Location,
    start: datetime | None = None,
    hours: int = 12,
    step_min: int = 30,
    providers: list[str] | None = None,
) -> dict:
    """Cheapest standard fare per provider for upcoming departure slots (not recorded).

    Like a fare calendar: shows whether waiting a little would be cheaper.
    """
    o, d = places.resolve(origin), places.resolve(destination)
    first = make_trip(o, d, start).when
    first = first.replace(second=0, microsecond=0)
    # Round up to the next slot boundary so no slot lies before the requested time.
    first += timedelta(minutes=-(first.hour * 60 + first.minute) % step_min)
    factors = calibration_factors(store)
    selected = [REGISTRY[k] for k in (providers or REGISTRY) if k in REGISTRY]
    slots = []
    for i in range(hours * 60 // step_min + 1):
        trip = make_trip(o, d, first + timedelta(minutes=i * step_min))
        quotes = [q for p in selected for q in p.quote(trip) if q.seats <= 4]
        apply_calibration(quotes, factors)
        best: dict[str, float] = {}
        for q in quotes:
            best[q.provider] = min(q.price, best.get(q.provider, q.price))
        slots.append({"when": trip.when.isoformat(timespec="minutes"), "prices": best})
    cheapest = min(slots, key=lambda s: min(s["prices"].values()))
    return {"slots": slots, "cheapest": {"when": cheapest["when"], "price": min(cheapest["prices"].values()),
                                         "provider": min(cheapest["prices"], key=cheapest["prices"].get)}}
