"""Tiny FastAPI app under test."""

import asyncio

from fastapi import FastAPI, HTTPException
from prometheus_client import Counter

_DB: dict[int, dict] = {
    1: {"id": 1, "name": "widget"},
    2: {"id": 2, "name": "gadget"},
}

# A custom business metric, declared the ordinary way: on prometheus_client's
# global default registry. No wiring into the test registry needed —
# pytest-fastprom reads the global registry and reports each test's delta.
CACHE_HITS = Counter("cache_hits", "Items served from the in-memory cache", ["region"])


def create_app() -> FastAPI:
    app = FastAPI()

    @app.get("/items/{item_id}")
    async def read_item(item_id: int, region: str = "eu") -> dict:
        item = _DB.get(item_id)
        if item is None:
            raise HTTPException(status_code=404, detail="not found")
        CACHE_HITS.labels(region).inc()
        return item

    @app.get("/search")
    async def search() -> dict:
        # Simulated slow path (e.g. unindexed query) — 250ms
        await asyncio.sleep(0.25)
        return {"results": list(_DB.values())}

    @app.get("/unstable")
    async def unstable(boom: bool = False) -> dict:
        # Flaky dependency: returns 500 when ?boom=true, else 200.
        if boom:
            raise HTTPException(status_code=500, detail="downstream blew up")
        return {"ok": True}

    return app
