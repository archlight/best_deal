# Best Deal: ride price comparison

A Skyscanner-style fare comparison for **Grab**, **Gojek** and **ComfortDelGro (Zig)** in Singapore.
Enter a route and see every option ranked **Best / Cheapest / Fastest**, plus a "cheapest time to go" chart for the next 12 hours.
**Every search and every price is recorded** in SQLite, so the Insights view can show who is usually cheapest, when surges hit and how each of your routes behaves.

## Quick start

```bash
pip install -r requirements.txt
python -m best_deal serve            # http://127.0.0.1:8000
```

Want to see Insights with data straight away? Generate a synthetic history in a **separate** database:

```bash
python -m best_deal --db data/demo.db seed --days 28 --per-day 12
python -m best_deal --db data/demo.db serve
```

### CLI

```bash
python -m best_deal search "Changi Airport T3" "Marina Bay Sands" --when 2026-09-25T18:30
python -m best_deal observe 12 Grab JustGrab 31.40      # record the price you actually saw for search #12
python -m best_deal insights                            # plain-language findings (add --json for everything)
```

Locations can be a built-in place name (fuzzy: `changi t3`, `jurong`), a `lat,lng` pair, or `{name, lat, lng}` over the API.
Set `BEST_DEAL_GEOCODER=nominatim` to look up any other address through OpenStreetMap.

## Where prices come from

Grab, Gojek and ComfortDelGro don't offer public fare APIs, so each provider in `best_deal/providers/` is an **estimator**:

| Provider | Model |
|---|---|
| Grab | Base + per-km + per-minute, platform fee and minimum fare per product (Saver, JustGrab, GrabCar 6, Premium). Demand-driven surge up to 2.0×, occasional promos. |
| Gojek | Same structure (GoCar Economy, GoCar, GoCar XL). Lower fees, gentler surge, more frequent promos. |
| ComfortDelGro | **Metered taxi** (flag-down plus 400 m/350 m steps, waiting time, 25% peak and 50% midnight surcharges, booking fee, Changi airport surcharge), shown as a price range. Also **Flat Fare**, **ComfortRIDE** and **MaxiCab** with milder dynamic pricing. |

Demand comes from time of day and weekday (weekday rush hours, Friday/Saturday nights, lunch), plus a deterministic 15-minute jitter per route. Repeated searches in the same window therefore agree, as they do in the real apps.

**Estimates are only a starting point. Real prices make it accurate.** After checking a provider's app, click **Record actual** on that result (or use `observe`). Each observation:

1. is stored with `source = "observed"` next to the estimate made in the same search;
2. overrides the estimate for that product in all insights;
3. calibrates future estimates. After `BEST_DEAL_CALIBRATION_MIN` (default 3) observations of a product, its estimates are scaled by the median observed/estimate ratio. The Estimate accuracy table shows the error.

To plug in a real price source (e.g. a partner API), implement `Provider.quote(trip) -> list[Quote]`, return quotes with `source="live"`, and register it in `providers/__init__.py`.

## What gets recorded

`searches`: when the search was made, the ride's local time, hour and weekday, origin and destination (name and coordinates), a `route_key` (origin and destination rounded to about 100 m), distance and drive time.

`quotes`: one row per product per search. Stores provider, product, seats, price and range, the raw model price, pickup ETA, trip time, surge multiplier, source (`estimate` / `observed` / `live`) and notes.

Export everything with **Export CSV** (`/api/export.csv`) for your own analysis.

## Insights

Comparisons use each provider's cheapest standard (4-seat or fewer) option per search. You can filter to observed-only or estimate-only data.

- **Who's cheapest**: win rate, average fare, price per km and average surge per provider
- **Price per km by hour**: per provider, normalised for trip distance
- **When rides are cheapest**: weekday × hour heatmap
- **Your routes**: usual winner, price range, cheapest and priciest hour to ride
- **Findings**: plain-language takeaways, e.g. "riding at 05:00 instead of 19:00 saves about $14"
- **Estimate accuracy**: observed ÷ estimated per product

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/search` | `{origin, destination, when?, providers?}`. Returns ranked quotes and records them. |
| POST | `/api/timeline` | Cheapest fare per provider for upcoming slots (not recorded) |
| POST | `/api/observations` | `{search_id, provider, product, price, pickup_eta_min?}` |
| GET | `/api/searches`, `/api/searches/{id}` | History (`?route_key=` to filter) |
| GET | `/api/insights` | `?source=all\|estimate\|observed&route_key=` |
| GET | `/api/places?q=` | Place autocomplete |
| GET | `/api/export.csv` | All quotes with search context |

Interactive docs are at `/docs`.

## Configuration

| Variable | Default | |
|---|---|---|
| `BEST_DEAL_DB` | `./data/best_deal.db` | SQLite file (or pass `--db`) |
| `BEST_DEAL_TZ` | `Asia/Singapore` | Local time for peak and surcharge rules |
| `BEST_DEAL_GEOCODER` | `none` | `nominatim` to enable OpenStreetMap lookups |
| `BEST_DEAL_CALIBRATION_MIN` | `3` | Observations needed before calibrating a product |
| `BEST_DEAL_PASSWORD` | unset | Require HTTP Basic auth (any username) |
| `LITESTREAM_REPLICA_URL` | unset | Container only: replicate the DB, e.g. `gcs://bucket/best_deal.db` |

## Deploy to Google Cloud Run

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
BEST_DEAL_PASSWORD='choose-a-password' ./deploy/cloudrun.sh
```

The script (safe to re-run) enables the needed APIs and creates:

- a Cloud Storage bucket `<project>-best-deal-data` for the price history
- a service account with access to that bucket only
- a Secret Manager secret for the password
- a Cloud Run service `best-deal` in `asia-southeast1`, built from the `Dockerfile` via Cloud Build

Then it prints the URL. Override `REGION`, `SERVICE` or `BUCKET` with environment variables.

**How the history survives:** Cloud Run disks are wiped whenever an instance stops. [Litestream](https://litestream.io) restores `best_deal.db` from the bucket at startup and streams every change back within about a second. The service runs with `--max-instances 1` because SQLite needs a single writer. It scales to zero when idle, so expect a cold start of a few seconds.

**Access:** with `BEST_DEAL_PASSWORD` set, the browser asks for a login (any username, that password). `/healthz` stays open. Without a password, anyone with the URL can search and add to your history.

Run the same container locally:

```bash
docker build -t best-deal .
docker run -p 8080:8080 -v "$PWD/data:/data" best-deal
```

## Development

```bash
pip install -r requirements-dev.txt
pytest
```
