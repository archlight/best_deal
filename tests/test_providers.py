from datetime import datetime

from best_deal import config
from best_deal.places import resolve
from best_deal.providers import REGISTRY
from best_deal.providers.base import demand_level
from best_deal.service import make_trip

TZ = config.TIMEZONE


def trip(o="Tampines", d="Raffles Place", when=datetime(2026, 9, 23, 14, 0, tzinfo=TZ)):
    return make_trip(resolve(o), resolve(d), when)


def test_every_provider_returns_positive_quotes():
    t = trip()
    for provider in REGISTRY.values():
        quotes = provider.quote(t)
        assert quotes
        for q in quotes:
            assert q.price > 0
            assert q.price_low <= q.price <= q.price_high
            assert q.pickup_eta_min >= 1
            assert q.model_price == q.price


def test_quotes_are_stable_within_a_time_window():
    a = [q.price for p in REGISTRY.values() for q in p.quote(trip(when=datetime(2026, 9, 23, 14, 1, tzinfo=TZ)))]
    b = [q.price for p in REGISTRY.values() for q in p.quote(trip(when=datetime(2026, 9, 23, 14, 12, tzinfo=TZ)))]
    assert a == b


def test_peak_is_pricier_than_off_peak():
    peak = trip(when=datetime(2026, 9, 23, 18, 30, tzinfo=TZ))  # Wednesday evening
    quiet = trip(when=datetime(2026, 9, 23, 10, 30, tzinfo=TZ))
    assert demand_level(peak.when) > demand_level(quiet.when)
    for provider in REGISTRY.values():
        assert min(q.price for q in provider.quote(peak)) > min(q.price for q in provider.quote(quiet))


def test_longer_trips_cost_more():
    short = trip("Bugis", "Clarke Quay")
    long = trip("Changi Airport T3", "Jurong East")
    for provider in REGISTRY.values():
        assert max(q.price for q in provider.quote(short)) < min(q.price for q in provider.quote(long)) * 2
        assert min(q.price for q in provider.quote(short)) < min(q.price for q in provider.quote(long))


def test_comfort_metered_taxi_surcharges():
    comfort = REGISTRY["comfort"]
    midnight = comfort.metered_quote(trip(when=datetime(2026, 9, 23, 1, 0, tzinfo=TZ)))
    assert midnight.surge == 1.5
    airport = comfort.metered_quote(trip("Changi Airport T3", "Bugis", when=datetime(2026, 9, 23, 19, 0, tzinfo=TZ)))
    assert any("airport surcharge $8" in n for n in airport.notes)


def test_grab_deeplink_carries_coordinates():
    q = REGISTRY["grab"].quote(trip())[0]
    assert q.deeplink.startswith("grab://open?") and "dropOffLatitude=1.284" in q.deeplink
