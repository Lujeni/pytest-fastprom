"""Tiny FastAPI app under test."""

import asyncio

from fastapi import FastAPI, HTTPException

_DB: dict[int, dict] = {
    1: {"id": 1, "name": "widget"},
    2: {"id": 2, "name": "gadget"},
}


def create_app() -> FastAPI:
    app = FastAPI()

    @app.get("/items/{item_id}")
    async def read_item(item_id: int) -> dict:
        item = _DB.get(item_id)
        if item is None:
            raise HTTPException(status_code=404, detail="not found")
        return item

    @app.get("/search")
    async def search() -> dict:
        # Simulated slow path (e.g. unindexed query) — 250ms
        await asyncio.sleep(0.25)
        return {"results": list(_DB.values())}

    return app
