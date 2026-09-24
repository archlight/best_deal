"""Turn the recorded price history into patterns: who wins, when prices peak, per-route advice.

Comparisons use each provider's cheapest standard (<= 4 seat) option per search.
When a real observed price exists for a search it replaces that provider's estimate.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict

from .storage import Store

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
SOURCES = ("all", "estimate", "observed")


def _mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 2) if values else None


def per_search(rows: list[dict], source: str = "all") -> list[dict]:
    """One record per search: context plus each provider's best standard price."""
    if source not in SOURCES:
        raise ValueError(f"source must be one of {SOURCES}")
    searches: dict[int, dict] = {}
    for r in rows:
        if r["seats"] > 4 or (source != "all" and r["source"] != source):
            continue
        s = searches.setdefault(r["search_id"], {
            "search_id": r["search_id"],
            "hour": r["local_hour"],
            "weekday": r["weekday"],
            "route_key": r["route_key"],
            "route": f"{r['origin_name']} → {r['dest_name']}",
            "distance_km": r["distance_km"],
            "trip_time": r["trip_time"],
            "prices": {},
            "observed": {},
            "surge": {},
        })
        is_obs = r["source"] == "observed"
        bucket = s["observed"] if is_obs else s["prices"]
        key = (r["provider"], r["product"])
        if key not in bucket or r["price"] < bucket[key]:
            bucket[key] = r["price"]
        if not is_obs:
            s["surge"][r["provider"]] = max(s["surge"].get(r["provider"], 0), r["surge"] or 1)
    out = []
    for s in searches.values():
        by_product = {**s.pop("prices"), **s.pop("observed")}  # observed overrides that product's estimate
        best: dict[str, float] = {}
        for (provider, _), price in by_product.items():
            best[provider] = min(price, best.get(provider, price))
        if not best:
            continue
        s["best"] = best
        s["winner"] = min(best, key=best.get)
        s["best_price"] = best[s["winner"]]
        s["spread"] = round(max(best.values()) - s["best_price"], 2) if len(best) > 1 else 0.0
        out.append(s)
    return out


def provider_stats(searches: list[dict]) -> list[dict]:
    prices: dict[str, list[float]] = defaultdict(list)
    per_km: dict[str, list[float]] = defaultdict(list)
    surges: dict[str, list[float]] = defaultdict(list)
    wins = Counter(s["winner"] for s in searches if len(s["best"]) > 1)
    contests = Counter(p for s in searches if len(s["best"]) > 1 for p in s["best"])
    for s in searches:
        for p, price in s["best"].items():
            prices[p].append(price)
            per_km[p].append(price / max(s["distance_km"], 0.5))
        for p, sg in s["surge"].items():
            surges[p].append(sg)
    return sorted(
        (
            {
                "provider": p,
                "quotes": len(prices[p]),
                "wins": wins.get(p, 0),
                "win_rate": round(wins.get(p, 0) / contests[p], 3) if contests[p] else None,
                "avg_price": _mean(prices[p]),
                "avg_price_per_km": _mean(per_km[p]),
                "avg_surge": _mean(surges[p]),
            }
            for p in prices
        ),
        key=lambda x: -(x["win_rate"] or 0),
    )


def hourly(searches: list[dict]) -> dict:
    """Average price per km by hour of day for each provider."""
    acc: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for s in searches:
        for p, price in s["best"].items():
            acc[p][s["hour"]].append(price / max(s["distance_km"], 0.5))
    return {
        p: [{"hour": h, "avg_price_per_km": _mean(by_hour.get(h, [])), "n": len(by_hour.get(h, []))} for h in range(24)]
        for p, by_hour in sorted(acc.items())
    }


def heatmap(searches: list[dict]) -> list[dict]:
    """Cheapest-available price per km for each weekday x hour cell that has data."""
    cells: dict[tuple[int, int], list[float]] = defaultdict(list)
    for s in searches:
        cells[(s["weekday"], s["hour"])].append(s["best_price"] / max(s["distance_km"], 0.5))
    return [
        {"weekday": wd, "day": WEEKDAYS[wd], "hour": h, "avg_price_per_km": _mean(v), "n": len(v)}
        for (wd, h), v in sorted(cells.items())
    ]


def routes(searches: list[dict], limit: int = 10) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for s in searches:
        grouped[s["route_key"]].append(s)
    out = []
    for key, items in grouped.items():
        by_hour: dict[int, list[float]] = defaultdict(list)
        for s in items:
            by_hour[s["hour"]].append(s["best_price"])
        hour_avgs = {h: statistics.fmean(v) for h, v in by_hour.items()}
        cheapest_hour = min(hour_avgs, key=hour_avgs.get)
        priciest_hour = max(hour_avgs, key=hour_avgs.get)
        winners = Counter(s["winner"] for s in items)
        top, top_n = winners.most_common(1)[0]
        prices = [s["best_price"] for s in items]
        out.append({
            "route_key": key,
            "route": items[-1]["route"],
            "distance_km": items[-1]["distance_km"],
            "searches": len(items),
            "avg_best_price": _mean(prices),
            "min_best_price": min(prices),
            "max_best_price": max(prices),
            "usual_winner": top,
            "usual_winner_share": round(top_n / len(items), 3),
            "cheapest_hour": cheapest_hour,
            "cheapest_hour_avg": round(hour_avgs[cheapest_hour], 2),
            "priciest_hour": priciest_hour,
            "priciest_hour_avg": round(hour_avgs[priciest_hour], 2),
            "avg_spread": _mean([s["spread"] for s in items]),
        })
    out.sort(key=lambda r: -r["searches"])
    return out[:limit]


def calibration(store: Store) -> list[dict]:
    """How far the estimates are from real observed prices, per product."""
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in store.calibration_pairs():
        grouped[(row["provider"], row["product"])].append(row["observed"] / row["estimated"])
    return [
        {
            "provider": p,
            "product": prod,
            "samples": len(r),
            "median_ratio": round(statistics.median(r), 3),
            "mean_abs_error_pct": round(statistics.fmean(abs(x - 1) for x in r) * 100, 1),
        }
        for (p, prod), r in sorted(grouped.items())
    ]


def _fmt_hour(h: int) -> str:
    return f"{h:02d}:00"


def findings(searches: list[dict], providers: list[dict], route_list: list[dict]) -> list[str]:
    """Plain-language takeaways from the patterns."""
    notes: list[str] = []
    contested = [s for s in searches if len(s["best"]) > 1]
    if not contested:
        return ["Not enough data yet: run a few searches across different times to see patterns."]
    top = providers[0]
    if top["win_rate"] is not None:
        notes.append(
            f"{top['provider']} was cheapest in {top['win_rate']:.0%} of {len(contested)} comparisons "
            f"(average {top['avg_price_per_km']:.2f}/km)."
        )
    avg_spread = statistics.fmean(s["spread"] for s in contested)
    notes.append(f"Comparing saved an average of ${avg_spread:.2f} per trip versus picking the priciest app.")

    by_hour: dict[int, list[float]] = defaultdict(list)
    for s in searches:
        by_hour[s["hour"]].append(s["best_price"] / max(s["distance_km"], 0.5))
    if len(by_hour) >= 3:
        overall = statistics.fmean(v for vals in by_hour.values() for v in vals)
        avgs = {h: statistics.fmean(v) for h, v in by_hour.items()}
        hi, lo = max(avgs, key=avgs.get), min(avgs, key=avgs.get)
        notes.append(
            f"Rides around {_fmt_hour(hi)} cost {avgs[hi] / overall - 1:+.0%} per km versus average; "
            f"around {_fmt_hour(lo)} they cost {avgs[lo] / overall - 1:+.0%}."
        )

    for r in route_list[:3]:
        if r["searches"] >= 3 and r["cheapest_hour"] != r["priciest_hour"]:
            saving = r["priciest_hour_avg"] - r["cheapest_hour_avg"]
            notes.append(
                f"{r['route']}: {r['usual_winner']} usually wins ({r['usual_winner_share']:.0%}); "
                f"riding at {_fmt_hour(r['cheapest_hour'])} instead of {_fmt_hour(r['priciest_hour'])} saves about ${saving:.2f}."
            )
    return notes


def build(store: Store, source: str = "all", route_key: str | None = None) -> dict:
    rows = store.quote_rows(route_key=route_key)
    searches = per_search(rows, source)
    prov = provider_stats(searches)
    route_list = routes(searches, limit=10 if route_key is None else 1)
    return {
        "source": source,
        "summary": {
            "searches": len(searches),
            "quotes": len(rows),
            "observed_quotes": sum(1 for r in rows if r["source"] == "observed"),
            "routes": len({s["route_key"] for s in searches}),
            "avg_spread": _mean([s["spread"] for s in searches if len(s["best"]) > 1]),
            "first": min((s["trip_time"] for s in searches), default=None),
            "last": max((s["trip_time"] for s in searches), default=None),
        },
        "providers": prov,
        "hourly": hourly(searches),
        "heatmap": heatmap(searches),
        "routes": route_list,
        "calibration": calibration(store),
        "findings": findings(searches, prov, route_list),
    }
