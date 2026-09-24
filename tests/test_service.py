from datetime import datetime

import pytest

from best_deal import config, service


def test_search_records_every_quote(store):
    r = service.search(store, "Tampines", "Raffles Place", datetime(2026, 9, 23, 8, 0))
    saved = store.get_search(r["search_id"])
    assert len(saved["quotes"]) == len(r["quotes"]) > 3
    assert saved["local_hour"] == 8 and saved["weekday"] == 2
    prices = [q["price"] for q in r["quotes"]]
    assert prices == sorted(prices)
    assert r["labels"]["cheapest"]["price"] == prices[0]


def test_search_without_record(store):
    r = service.search(store, "Bugis", "Novena", record=False)
    assert r["search_id"] is None
    assert store.list_searches() == []


def test_provider_filter(store):
    r = service.search(store, "Bugis", "Novena", providers=["gojek"], record=False)
    assert {q["provider"] for q in r["quotes"]} == {"Gojek"}


def test_naive_time_is_local(store):
    r = service.search(store, "Bugis", "Novena", datetime(2026, 9, 23, 8, 0), record=False)
    assert r["trip"]["when"] == "2026-09-23T08:00+08:00"


def test_observation_reports_error_and_calibrates(store, monkeypatch):
    monkeypatch.setattr(config, "CALIBRATION_MIN_SAMPLES", 2)
    when = datetime(2026, 9, 23, 11, 0)
    for _ in range(2):
        r = service.search(store, "Tampines", "Raffles Place", when)
        est = next(q for q in r["quotes"] if q["product"] == "JustGrab")
        obs = service.record_observation(store, r["search_id"], "Grab", "JustGrab", round(est["model_price"] * 1.2, 2))
        assert obs["estimate_error_pct"] == pytest.approx(20, abs=0.5)
    r = service.search(store, "Tampines", "Raffles Place", when)
    q = next(q for q in r["quotes"] if q["product"] == "JustGrab")
    assert q["price"] == pytest.approx(q["model_price"] * 1.2, abs=0.2)
    assert any("calibrated" in n for n in q["notes"])


def test_observation_validation(store):
    with pytest.raises(LookupError):
        service.record_observation(store, 999, "Grab", "JustGrab", 10)
    r = service.search(store, "Bugis", "Novena")
    with pytest.raises(ValueError):
        service.record_observation(store, r["search_id"], "Grab", "JustGrab", 0)


def test_timeline_starts_at_or_after_requested_time(store):
    t = service.timeline(store, "Bugis", "Novena", datetime(2026, 9, 23, 6, 10), hours=2)
    assert t["slots"][0]["when"] == "2026-09-23T06:30+08:00"
    assert len(t["slots"]) == 5
    assert store.list_searches() == []
    assert t["cheapest"]["price"] == min(min(s["prices"].values()) for s in t["slots"])
