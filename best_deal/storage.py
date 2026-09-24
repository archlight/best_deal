"""SQLite persistence. Every search and every quote (estimated, observed or live) is kept."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .providers.base import Quote, Trip

SCHEMA = """
CREATE TABLE IF NOT EXISTS searches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at   TEXT NOT NULL,      -- UTC ISO timestamp the search was made
    trip_time    TEXT NOT NULL,      -- local ISO time the ride is for
    local_hour   INTEGER NOT NULL,
    weekday      INTEGER NOT NULL,   -- 0 = Monday
    origin_name  TEXT NOT NULL,
    origin_lat   REAL NOT NULL,
    origin_lng   REAL NOT NULL,
    dest_name    TEXT NOT NULL,
    dest_lat     REAL NOT NULL,
    dest_lng     REAL NOT NULL,
    route_key    TEXT NOT NULL,
    distance_km  REAL NOT NULL,
    duration_min REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_searches_route ON searches(route_key);
CREATE INDEX IF NOT EXISTS idx_searches_time ON searches(trip_time);

CREATE TABLE IF NOT EXISTS quotes (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    search_id      INTEGER NOT NULL REFERENCES searches(id) ON DELETE CASCADE,
    recorded_at    TEXT NOT NULL,
    provider       TEXT NOT NULL,
    product        TEXT NOT NULL,
    seats          INTEGER NOT NULL,
    price          REAL NOT NULL,
    price_low      REAL NOT NULL,
    price_high     REAL NOT NULL,
    model_price    REAL,
    currency       TEXT NOT NULL,
    pickup_eta_min REAL,
    trip_min       REAL,
    surge          REAL,
    source         TEXT NOT NULL,   -- estimate | observed | live
    notes          TEXT
);
CREATE INDEX IF NOT EXISTS idx_quotes_search ON quotes(search_id);
CREATE INDEX IF NOT EXISTS idx_quotes_provider ON quotes(provider, product);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        # A shared connection is required for in-memory databases (tests).
        self._memory = sqlite3.connect(":memory:", check_same_thread=False) if self.path == ":memory:" else None
        with self.connect() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = self._memory or sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            if db is not self._memory:
                db.close()

    def add_search(self, trip: Trip) -> int:
        with self.connect() as db:
            cur = db.execute(
                """INSERT INTO searches (created_at, trip_time, local_hour, weekday, origin_name, origin_lat,
                   origin_lng, dest_name, dest_lat, dest_lng, route_key, distance_km, duration_min)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    utcnow(), trip.when.isoformat(timespec="minutes"), trip.when.hour, trip.when.weekday(),
                    trip.origin.name, trip.origin.lat, trip.origin.lng,
                    trip.destination.name, trip.destination.lat, trip.destination.lng,
                    trip.route_key, trip.distance_km, trip.duration_min,
                ),
            )
            return cur.lastrowid

    def add_quotes(self, search_id: int, quotes: list[Quote]) -> list[int]:
        now = utcnow()
        ids = []
        with self.connect() as db:
            for q in quotes:
                cur = db.execute(
                    """INSERT INTO quotes (search_id, recorded_at, provider, product, seats, price, price_low,
                       price_high, model_price, currency, pickup_eta_min, trip_min, surge, source, notes)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        search_id, now, q.provider, q.product, q.seats, q.price, q.price_low, q.price_high,
                        q.model_price, q.currency, q.pickup_eta_min, q.trip_min, q.surge, q.source,
                        "; ".join(q.notes),
                    ),
                )
                ids.append(cur.lastrowid)
        return ids

    def get_search(self, search_id: int) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM searches WHERE id = ?", (search_id,)).fetchone()
            if not row:
                return None
            quotes = db.execute("SELECT * FROM quotes WHERE search_id = ? ORDER BY price", (search_id,)).fetchall()
        return {**dict(row), "quotes": [dict(q) for q in quotes]}

    def list_searches(self, limit: int = 50, route_key: str | None = None) -> list[dict]:
        sql = """SELECT s.*,
                   (SELECT MIN(price) FROM quotes q WHERE q.search_id = s.id AND q.seats <= 4) AS best_price,
                   (SELECT provider FROM quotes q WHERE q.search_id = s.id AND q.seats <= 4
                      ORDER BY price LIMIT 1) AS best_provider,
                   (SELECT COUNT(*) FROM quotes q WHERE q.search_id = s.id AND q.source = 'observed') AS observed
                 FROM searches s"""
        params: tuple = ()
        if route_key:
            sql += " WHERE s.route_key = ?"
            params = (route_key,)
        sql += " ORDER BY s.id DESC LIMIT ?"
        with self.connect() as db:
            return [dict(r) for r in db.execute(sql, (*params, limit))]

    def quote_rows(self, route_key: str | None = None) -> list[dict]:
        """All quotes joined with their search context — the raw material for insights."""
        sql = """SELECT q.*, s.trip_time, s.local_hour, s.weekday, s.route_key, s.origin_name, s.dest_name,
                        s.distance_km, s.duration_min, s.created_at
                 FROM quotes q JOIN searches s ON s.id = q.search_id"""
        params: tuple = ()
        if route_key:
            sql += " WHERE s.route_key = ?"
            params = (route_key,)
        with self.connect() as db:
            return [dict(r) for r in db.execute(sql + " ORDER BY q.id", params)]

    def calibration_pairs(self) -> list[dict]:
        """Observed prices paired with the model estimate made for the same search and product."""
        sql = """SELECT o.provider, o.product, o.price AS observed, e.model_price AS estimated
                 FROM quotes o JOIN quotes e
                   ON e.search_id = o.search_id AND e.provider = o.provider AND e.product = o.product
                  AND e.source = 'estimate'
                 WHERE o.source = 'observed' AND e.model_price > 0"""
        with self.connect() as db:
            return [dict(r) for r in db.execute(sql)]
