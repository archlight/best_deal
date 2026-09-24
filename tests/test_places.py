import pytest

from best_deal.geo import Location, road_distance_km
from best_deal.places import LocationNotFound, resolve, search_places


def test_resolve_by_name_is_fuzzy():
    assert resolve("changi t3").name == "Changi Airport T3"
    assert resolve("marina bay").name == "Marina Bay Sands"


def test_resolve_lat_lng_and_dict():
    assert resolve("1.3, 103.8") == Location("1.3, 103.8", 1.3, 103.8)
    assert resolve({"name": "Home", "lat": 1.35, "lng": 103.9}).name == "Home"


def test_unknown_location_raises():
    with pytest.raises(LocationNotFound):
        resolve("definitely not a place")


def test_search_places_prefers_prefix():
    assert search_places("jur")[0].name == "Jurong East"


def test_road_distance_is_plausible():
    km = road_distance_km(resolve("Changi Airport T3"), resolve("Marina Bay Sands"))
    assert 17 < km < 25
