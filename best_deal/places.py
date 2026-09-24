"""Location resolution: built-in Singapore places, "lat,lng" strings and optional geocoding."""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request

from . import config
from .geo import Location

PLACES: list[Location] = [
    Location("Changi Airport T1", 1.3614, 103.9893),
    Location("Changi Airport T2", 1.3554, 103.9887),
    Location("Changi Airport T3", 1.3570, 103.9870),
    Location("Changi Airport T4", 1.3383, 103.9832),
    Location("Jewel Changi", 1.3602, 103.9894),
    Location("Marina Bay Sands", 1.2834, 103.8607),
    Location("Gardens by the Bay", 1.2816, 103.8636),
    Location("Raffles Place", 1.2840, 103.8514),
    Location("Tanjong Pagar", 1.2764, 103.8455),
    Location("Chinatown", 1.2838, 103.8436),
    Location("Clarke Quay", 1.2906, 103.8465),
    Location("Bugis", 1.3008, 103.8559),
    Location("Orchard Road (ION)", 1.3040, 103.8318),
    Location("Dhoby Ghaut", 1.2990, 103.8456),
    Location("Little India", 1.3066, 103.8518),
    Location("Novena", 1.3204, 103.8438),
    Location("Toa Payoh", 1.3327, 103.8474),
    Location("Bishan", 1.3510, 103.8485),
    Location("Ang Mo Kio", 1.3700, 103.8496),
    Location("Serangoon (NEX)", 1.3508, 103.8723),
    Location("Paya Lebar", 1.3181, 103.8930),
    Location("Tampines", 1.3531, 103.9452),
    Location("Pasir Ris", 1.3730, 103.9493),
    Location("Bedok", 1.3240, 103.9300),
    Location("East Coast Park", 1.3008, 103.9122),
    Location("Punggol", 1.4052, 103.9024),
    Location("Sengkang", 1.3916, 103.8954),
    Location("Woodlands", 1.4370, 103.7865),
    Location("Yishun", 1.4295, 103.8350),
    Location("Jurong East", 1.3331, 103.7422),
    Location("Clementi", 1.3150, 103.7650),
    Location("Buona Vista", 1.3072, 103.7900),
    Location("one-north", 1.2995, 103.7874),
    Location("NUS (Kent Ridge)", 1.2966, 103.7764),
    Location("HarbourFront (VivoCity)", 1.2644, 103.8222),
    Location("Sentosa", 1.2494, 103.8303),
    Location("Holland Village", 1.3112, 103.7961),
    Location("Bukit Timah", 1.3294, 103.8021),
    Location("Boon Lay", 1.3386, 103.7058),
    Location("Tuas", 1.3200, 103.6500),
    Location("Singapore Zoo", 1.4043, 103.7930),
    Location("Punggol Coney Island", 1.4100, 103.9220),
]

_LATLNG_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


class LocationNotFound(ValueError):
    pass


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def search_places(query: str, limit: int = 8) -> list[Location]:
    q = _normalize(query)
    if not q:
        return PLACES[:limit]
    exact = [p for p in PLACES if _normalize(p.name) == q]
    prefix = [p for p in PLACES if _normalize(p.name).startswith(q) and p not in exact]
    words = q.split()
    contains = [
        p for p in PLACES
        if p not in exact and p not in prefix and all(w in _normalize(p.name) for w in words)
    ]
    return (exact + prefix + contains)[:limit]


def _nominatim(query: str) -> Location | None:
    params = urllib.parse.urlencode({"q": query, "format": "json", "limit": 1, "countrycodes": "sg"})
    req = urllib.request.Request(
        f"https://nominatim.openstreetmap.org/search?{params}",
        headers={"User-Agent": "best-deal-ride-compare/0.1"},
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        results = json.load(resp)
    if not results:
        return None
    r = results[0]
    return Location(r.get("display_name", query).split(",")[0], float(r["lat"]), float(r["lon"]))


def resolve(value: str | dict | Location) -> Location:
    """Turn user input into a Location. Accepts a place name, "lat,lng" or {name, lat, lng}."""
    if isinstance(value, Location):
        return value
    if isinstance(value, dict):
        try:
            return Location(value.get("name") or f"{value['lat']},{value['lng']}", float(value["lat"]), float(value["lng"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise LocationNotFound(f"Invalid location object: {value!r}") from exc
    text = str(value).strip()
    m = _LATLNG_RE.match(text)
    if m:
        return Location(text, float(m.group(1)), float(m.group(2)))
    matches = search_places(text, limit=1)
    if matches:
        return matches[0]
    if config.GEOCODER == "nominatim":
        try:
            found = _nominatim(text)
        except OSError:
            found = None
        if found:
            return found
    raise LocationNotFound(f"Unknown location: {text!r}. Use a known place or 'lat,lng'.")
