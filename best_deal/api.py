"""HTTP API and static web UI."""

from __future__ import annotations

import csv
import io
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, insights, places, service
from .providers import REGISTRY
from .storage import Store

STATIC = Path(__file__).parent / "static"


class SearchRequest(BaseModel):
    origin: str | dict
    destination: str | dict
    when: datetime | None = Field(None, description="Local ride time; defaults to now")
    providers: list[str] | None = None


class TimelineRequest(SearchRequest):
    hours: int = Field(12, ge=1, le=48)
    step_min: int = Field(30, ge=15, le=120)


class ObservationRequest(BaseModel):
    search_id: int
    provider: str
    product: str
    price: float = Field(gt=0)
    pickup_eta_min: float | None = Field(None, ge=0)
    seats: int | None = Field(None, ge=1, le=13)


def create_app(store: Store | None = None) -> FastAPI:
    store = store or Store(config.DB_PATH)
    app = FastAPI(title="Best Deal", description="Compare Grab, Gojek and ComfortDelGro fares.")
    app.state.store = store

    @app.get("/api/places")
    def list_places(q: str = "", limit: int = Query(8, ge=1, le=50)):
        return [p.as_dict() for p in places.search_places(q, limit)]

    @app.get("/api/providers")
    def list_providers():
        return [{"key": k, "name": p.name} for k, p in REGISTRY.items()]

    @app.post("/api/search")
    def do_search(req: SearchRequest):
        try:
            return service.search(store, req.origin, req.destination, req.when, req.providers)
        except places.LocationNotFound as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/timeline")
    def do_timeline(req: TimelineRequest):
        try:
            return service.timeline(
                store, req.origin, req.destination, req.when, req.hours, req.step_min, req.providers
            )
        except places.LocationNotFound as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/observations", status_code=201)
    def add_observation(req: ObservationRequest):
        try:
            return service.record_observation(store, **req.model_dump())
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/searches")
    def list_searches(limit: int = Query(50, ge=1, le=500), route_key: str | None = None):
        return store.list_searches(limit, route_key)

    @app.get("/api/searches/{search_id}")
    def get_search(search_id: int):
        found = store.get_search(search_id)
        if not found:
            raise HTTPException(404, "search not found")
        return found

    @app.get("/api/insights")
    def get_insights(source: str = Query("all", pattern="^(all|estimate|observed)$"), route_key: str | None = None):
        return insights.build(store, source, route_key)

    @app.get("/api/export.csv")
    def export_csv():
        rows = store.quote_rows()
        buf = io.StringIO()
        if rows:
            writer = csv.DictWriter(buf, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        buf.seek(0)
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=best_deal_quotes.csv"},
        )

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    return app
