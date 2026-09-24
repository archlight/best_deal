from datetime import datetime

from best_deal import insights, service
from best_deal.seed import seed


def test_empty_database(store):
    data = insights.build(store)
    assert data["summary"]["searches"] == 0
    assert "Not enough data" in data["findings"][0]


def test_observed_price_overrides_only_its_product(store):
    r = service.search(store, "Tampines", "Raffles Place", datetime(2026, 9, 23, 11, 0))
    grab = [q for q in r["quotes"] if q["provider"] == "Grab" and q["seats"] <= 4]
    cheapest_grab = min(q["price"] for q in grab)
    # Observing an expensive premium fare must not replace Grab's cheaper standard option.
    service.record_observation(store, r["search_id"], "Grab", "GrabCar Premium", 99.0)
    [s] = insights.per_search(store.quote_rows())
    assert s["best"]["Grab"] == cheapest_grab
    # Observing the cheap product itself does override the estimate.
    service.record_observation(store, r["search_id"], "Grab", "GrabCar Saver", 1.0)
    [s] = insights.per_search(store.quote_rows())
    assert s["best"]["Grab"] == 1.0 and s["winner"] == "Grab"


def test_seeded_history_produces_patterns(store):
    seed(store, days=7, per_day=10)
    data = insights.build(store)
    assert data["summary"]["searches"] == 70
    assert sum(p["wins"] for p in data["providers"]) == 70
    assert set(data["hourly"]) == {"Grab", "Gojek", "ComfortDelGro"}
    assert all(len(v) == 24 for v in data["hourly"].values())
    assert data["routes"] and data["heatmap"]
    assert len(data["findings"]) >= 3

    observed = insights.build(store, source="observed")
    assert observed["summary"]["searches"] <= data["summary"]["searches"]
    assert data["calibration"]


def test_route_filter(store):
    a = service.search(store, "Tampines", "Raffles Place")
    service.search(store, "Bugis", "Novena")
    data = insights.build(store, route_key=a["trip"]["route_key"])
    assert data["summary"]["searches"] == 1
