"""Command line: `python -m best_deal serve|search|insights|seed`."""

from __future__ import annotations

import argparse
import json
from datetime import datetime

from . import config, insights, service
from . import seed as seed_mod
from .places import LocationNotFound
from .storage import Store


def _print_search(result: dict) -> None:
    t = result["trip"]
    print(f"\n{t['origin']['name']} → {t['destination']['name']}  "
          f"{t['distance_km']} km, ~{t['duration_min']:.0f} min  ({t['when']})\n")
    print(f"{'Provider':<15}{'Product':<18}{'Price':>10}{'Range':>16}{'Pickup':>9}{'Surge':>7}")
    for q in result["quotes"]:
        rng = f"{q['price_low']:.2f}–{q['price_high']:.2f}" if q["price_low"] != q["price_high"] else ""
        print(f"{q['provider']:<15}{q['product']:<18}{q['price']:>10.2f}{rng:>16}"
              f"{q['pickup_eta_min']:>7.0f}m{q['surge']:>7.2f}")
    labels = result["labels"]
    print(f"\nCheapest: {labels['cheapest']['provider']} {labels['cheapest']['product']} ${labels['cheapest']['price']:.2f}")
    print(f"Fastest:  {labels['fastest']['provider']} {labels['fastest']['product']} ({labels['fastest']['minutes']:.0f} min door to door)")
    print(f"Best:     {labels['best']['provider']} {labels['best']['product']} ${labels['best']['price']:.2f}")
    if result["search_id"]:
        print(f"\nRecorded as search #{result['search_id']}.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="best_deal", description=__doc__)
    parser.add_argument("--db", default=str(config.DB_PATH), help="SQLite database path")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_serve = sub.add_parser("serve", help="Run the web app")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)

    p_search = sub.add_parser("search", help="Compare prices for a route")
    p_search.add_argument("origin")
    p_search.add_argument("destination")
    p_search.add_argument("--when", type=datetime.fromisoformat, help="Local time, e.g. 2026-09-24T08:30")
    p_search.add_argument("--no-record", action="store_true")
    p_search.add_argument("--json", action="store_true")

    p_obs = sub.add_parser("observe", help="Record a price you saw in an app for a search")
    p_obs.add_argument("search_id", type=int)
    p_obs.add_argument("provider")
    p_obs.add_argument("product")
    p_obs.add_argument("price", type=float)

    p_ins = sub.add_parser("insights", help="Show patterns from recorded prices")
    p_ins.add_argument("--source", choices=insights.SOURCES, default="all")
    p_ins.add_argument("--json", action="store_true")

    p_seed = sub.add_parser("seed", help="Generate synthetic history (use a separate --db)")
    p_seed.add_argument("--days", type=int, default=28)
    p_seed.add_argument("--per-day", type=int, default=12)

    args = parser.parse_args(argv)
    store = Store(args.db)

    if args.cmd == "serve":
        import uvicorn

        from .api import create_app

        uvicorn.run(create_app(store), host=args.host, port=args.port)
    elif args.cmd == "search":
        try:
            result = service.search(store, args.origin, args.destination, args.when, record=not args.no_record)
        except LocationNotFound as exc:
            parser.error(str(exc))
        print(json.dumps(result, indent=2)) if args.json else _print_search(result)
    elif args.cmd == "observe":
        print(json.dumps(service.record_observation(store, args.search_id, args.provider, args.product, args.price), indent=2))
    elif args.cmd == "insights":
        data = insights.build(store, args.source)
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            print("\n".join(f"• {f}" for f in data["findings"]))
    elif args.cmd == "seed":
        n = seed_mod.seed(store, args.days, args.per_day)
        print(f"Recorded {n} synthetic searches in {args.db}")


if __name__ == "__main__":
    main()
